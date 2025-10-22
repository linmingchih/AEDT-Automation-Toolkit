import os
import sys 
import re
import uuid
import tempfile
import json
import tempfile
from collections import defaultdict

import numpy as np
import skrf as rf
from ansys.aedt.core import Circuit
from ansys.aedt.core.generic.constants import Setups

project_path = sys.argv[1]


def format_with_unit(value, unit):
    if value is None:
        return f'0{unit}'
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed.lower().endswith(unit.lower()):
            return trimmed
        return f'{trimmed}{unit}'
    return f'{value:g}{unit}'


def _build_diff_list(diff_map):
    diff_pairs = []
    for pair, pol_map in diff_map.items():
        pos = pol_map.get('positive')
        neg = pol_map.get('negative')
        if pos is None or neg is None:
            raise ValueError(f'Differential pair "{pair}" is missing positive or negative port definition.')
        diff_pairs.append((pos, neg))
    diff_pairs.sort(key=lambda item: min(item))
    return diff_pairs


def load_configuration(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    ports = data.get('ports', [])
    port_name_map = {entry['sequence']: entry['name'] for entry in ports if 'sequence' in entry and 'name' in entry}

    tx_ports = []
    rx_ports = []
    tx_diff_map = defaultdict(dict)
    rx_diff_map = defaultdict(dict)

    for entry in sorted(ports, key=lambda item: item.get('sequence', 0)):
        sequence = entry.get('sequence')
        role = entry.get('component_role')
        net_type = entry.get('net_type')
        pair = entry.get('pair')
        polarity = (entry.get('polarity') or '').lower()

        if sequence is None or role is None or net_type is None:
            continue

        if net_type == 'single':
            if role == 'controller':
                tx_ports.append(sequence)
            elif role == 'dram':
                rx_ports.append(sequence)
        elif net_type == 'differential' and pair:
            if polarity not in {'positive', 'negative'}:
                raise ValueError(f'Unexpected polarity "{entry.get("polarity")}" for differential pair "{pair}".')
            if role == 'controller':
                tx_diff_map[pair][polarity] = sequence
            elif role == 'dram':
                rx_diff_map[pair][polarity] = sequence

    tx_diff_ports = _build_diff_list(tx_diff_map)
    rx_diff_ports = _build_diff_list(rx_diff_map)

    cct_settings = data.get('cct_settings', {})
    touchstone_path = data.get('touchstone_path')

    if not touchstone_path:
        raise ValueError('Touchstone path is not defined in the project JSON.')

    return {
        'touchstone_path': touchstone_path,
        'tx_ports': tx_ports,
        'rx_ports': rx_ports,
        'tx_diff_ports': tx_diff_ports,
        'rx_diff_ports': rx_diff_ports,
        'cct_settings': cct_settings,
        'port_name_map': port_name_map
    }


def build_cct_parameters(settings):
    threshold = settings.get('sparam_threshold_db', -40.0)
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        threshold = -40.0
    return {
        'vhigh': format_with_unit(settings.get('tx_vhigh', 0.8), 'V'),
        't_rise': format_with_unit(settings.get('tx_rise_time', 30.0), 'ps'),
        'unit_interval': format_with_unit(settings.get('unit_interval', 133.0), 'ps'),
        'res_tx': format_with_unit(settings.get('tx_resistance', 40.0), 'ohm'),
        'cap_tx': format_with_unit(settings.get('tx_capacitance', 1.0), 'pF'),
        'res_rx': format_with_unit(settings.get('rx_resistance', 30.0), 'ohm'),
        'cap_rx': format_with_unit(settings.get('rx_capacitance', 1.8), 'pF'),
        'tstep': format_with_unit(settings.get('transient_step', 100.0), 'ps'),
        'tstop': format_with_unit(settings.get('transient_stop', 3.0), 'ns'),
        'aedt_version': str(settings.get('aedt_version', '2025.1')),
        'sparam_threshold_db': threshold
    }


def integrate_nonuniform(x_list, y_list):
    integral = 0.0
    for i in range(len(x_list) - 1):
        # 使用梯形公式
        dx = x_list[i + 1] - x_list[i]
        integral += 0.5 * (y_list[i] + y_list[i + 1]) * dx
    return integral


def get_sig_isi(time_list, voltage_list, unit_interval):
    """
    sig: 寬度為 unit_interval 的滑動視窗內，∫v(t)dt 的最大值（視窗完全落在資料範圍內）
    isi: 除了該最大視窗以外，∫|v(t)|dt
    """
    t = np.asarray(time_list, dtype=float)
    v = np.asarray(voltage_list, dtype=float)
    if t.ndim != 1 or v.ndim != 1 or t.size != v.size:
        raise ValueError("time_list 與 voltage_list 必須為一維且長度相同")
    if unit_interval <= 0:
        raise ValueError("unit_interval 必須為正數")

    # 依時間排序
    order = np.argsort(t)
    t = t[order]
    v = v[order]

    if t[-1] - t[0] < unit_interval:
        raise ValueError("資料時間範圍小於 unit_interval，無法形成完整視窗")

    # 累積積分（梯形法）
    dt = np.diff(t)
    trap = np.concatenate([[0.0], np.cumsum((v[:-1] + v[1:]) * 0.5 * dt)])
    trap_abs = np.concatenate([[0.0], np.cumsum((np.abs(v[:-1]) + np.abs(v[1:])) * 0.5 * dt)])
    total_abs = trap_abs[-1]

    # 僅遍歷「能形成完整視窗」的起點：t[i] + UI <= t[-1]
    n = len(t)
    # 最後可用起點的索引上限（滿足 t[i] + UI <= t[-1]）
    last_i = np.searchsorted(t, t[-1] - unit_interval, side="right") - 1
    if last_i < 0:
        raise ValueError("沒有任何起點能形成完整視窗")

    sig_max = -np.inf
    best_i = best_j = 0
    best_t_end = None
    j = 0

    for i in range(last_i + 1):
        t_end = t[i] + unit_interval

        # 向右移動 j，使得 t[j] <= t_end < t[j+1]（或 j 到尾）
        while j + 1 < n and t[j + 1] <= t_end:
            j += 1

        # 此時 t_end 一定 <= t[-1]，不會超界
        integ = trap[j] - trap[i]
        # 若 t_end 在 (t[j], t[j+1])，補最後一段梯形
        if j + 1 < n and t[j] < t_end < t[j + 1]:
            v_end = v[j] + (v[j + 1] - v[j]) * (t_end - t[j]) / (t[j + 1] - t[j])
            integ += 0.5 * (v[j] + v_end) * (t_end - t[j])

        if integ > sig_max:
            sig_max = integ
            best_i, best_j, best_t_end = i, j, t_end

    # 以最佳視窗計算 |v| 的積分，供 isi 使用
    i, j, t_end = best_i, best_j, best_t_end
    integ_abs = (trap_abs[j] - trap_abs[i])
    if j + 1 < n and t[j] < t_end < t[j + 1]:
        v_end = v[j] + (v[j + 1] - v[j]) * (t_end - t[j]) / (t[j + 1] - t[j])
        integ_abs += 0.5 * (abs(v[j]) + abs(v_end)) * (t_end - t[j])

    sig = float(sig_max)
    isi = float(total_abs - integ_abs)
    return sig, isi




class Tx:
    def __init__(self, pid, vhigh, t_rise, ui, res_tx, cap_tx):
        self.pid = pid
        self.active = [f"V{pid} netb_{pid} 0 PULSE(0 {vhigh} 1e-10 {t_rise} {t_rise} {ui} 1.5e+100)",
                       f"R{pid} netb_{pid} net_{pid} {res_tx}",
                       f"C{pid} netb_{pid} 0 {cap_tx}"]
        self.passive = [f"R{pid} netb_{pid} net_{pid} {res_tx}",
                        f"C{pid} netb_{pid} 0 {cap_tx}"]

    def get_netlist(self, active=True):
        if active:
            return self.active
        else:
            return self.passive
        

class Tx_diff:
    def __init__(self, pid_pos, pid_neg, vhigh, t_rise, ui, res_tx, cap_tx):
        self.pid_pos = pid_pos
        self.pid_neg = pid_neg
        
        self.active = [f"V{pid_pos} netb_{pid_pos} 0 PULSE(0 0.5*{vhigh} 1e-10 {t_rise} {t_rise} {ui} 1.5e+100)",
                       f"R{pid_pos} netb_{pid_pos} net_{pid_pos} {res_tx}",
                       f"C{pid_pos} netb_{pid_pos} 0 {cap_tx}",
                       f"V{pid_neg} netb_{pid_neg} 0 PULSE(0 -0.5*{vhigh} 1e-10 {t_rise} {t_rise} {ui} 1.5e+100)",
                       f"R{pid_neg} netb_{pid_neg} net_{pid_neg} {res_tx}",
                       f"C{pid_neg} netb_{pid_neg} 0 {cap_tx}"]
        
        self.passive = [f"R{pid_pos} netb_{pid_pos} net_{pid_pos} {res_tx}",
                        f"C{pid_pos} netb_{pid_pos} 0 {cap_tx}",
                        f"R{pid_neg} netb_{pid_neg} net_{pid_neg} {res_tx}",
                        f"C{pid_neg} netb_{pid_neg} 0 {cap_tx}"]

    def get_netlist(self, active=True):
        if active:
            return self.active
        else:
            return self.passive
        

        
    
class Rx:
    def __init__(self, pid, res_rx, cap_rx):
        self.pid = pid
        self.netlist = [f'R{pid} net_{pid} 0 {res_rx}', 
                        f'C{pid} net_{pid} 0 {cap_rx}']
        self.waveforms = {}
        
    def get_netlist(self):
        return self.netlist
    
class Rx_diff:
    def __init__(self, pid_pos, pid_neg, res_rx, cap_rx):
        self.pid_pos = pid_pos
        self.pid_neg = pid_neg
        
        self.netlist = [f'R{pid_pos} net_{pid_pos} 0 {res_rx}', 
                        f'C{pid_pos} net_{pid_pos} 0 {cap_rx}',
                        f'R{pid_neg} net_{pid_neg} 0 {res_rx}', 
                        f'C{pid_neg} net_{pid_neg} 0 {cap_rx}',]
        self.waveforms = {}
        
    def get_netlist(self):
        return self.netlist    
    
    
    
class Design:
    def __init__(self, tstep='100ps', tstop='3ns', aedt_version='2025.1'):
        self.netlist_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.cir")
        open(self.netlist_path, 'w').close()
        
    
        self.circuit = circuit = Circuit(version=aedt_version, 
                                         non_graphical=True,
                                         close_on_exit=True,)
    
        circuit.add_netlist_datablock(self.netlist_path)
        self.setup = circuit.create_setup('myTransient', Setups.NexximTransient)
        self.setup.props['TransientData'] = [tstep, tstop]
        self.circuit.save_project()

    def run(self, netlist):
        with open(self.netlist_path, 'w') as f:
            f.write(netlist)
            
        self.circuit.odesign.InvalidateSolution('myTransient')
        self.circuit.save_project()
        self.circuit.analyze('myTransient')
        self.circuit.save_project()
        
        result = {}
        for v in self.circuit.post.available_report_quantities():
            data = self.circuit.post.get_solution_data(v, domain='Time')
            x = [1e3*i for i in data.primary_sweep_values]
            y = [1e-3*i for i in data.data_real()]
            m = re.search(r'net_(\d+)', v)
            if m:
                number = int(m.group(1))
                result[number] = (x, y)
        return result
    
class CCT:
    def __init__(self, snp_path, tx_ports, rx_ports, tx_diff_ports, rx_diff_ports, port_name_map=None, aedt_version='2025.1'):
        self.snp_path = os.path.abspath(snp_path).replace('\\', '/')
        
        self.tx_ports = tx_ports
        self.rx_ports = rx_ports
        self.tx_diff_ports = tx_diff_ports
        self.rx_diff_ports = rx_diff_ports 
        self.port_name_map = port_name_map or {}
        self.aedt_version = aedt_version
        
        self.txs = []
        self.rxs = []

        self.network = rf.Network(self.snp_path)
        self.total_ports = self.network.nports
        self.all_ports = list(range(1, self.total_ports + 1))
        self._channel_options = 'INTERPOLATION=LINEAR INTDATTYP=MA HIGHPASS=10 LOWPASS=10 convolution=1 enforce_passivity=0 Noisemodel=External'
        self._temp_dir = tempfile.mkdtemp(prefix='cct_reduced_')
        self._reduced_cache = {}
        self._port_pair_map = {}
        for pos, neg in list(self.tx_diff_ports) + list(self.rx_diff_ports):
            pair = {pos, neg}
            self._port_pair_map[pos] = pair
            self._port_pair_map[neg] = pair

        # Cache the original full network path for completeness.
        self._reduced_cache[tuple(self.all_ports)] = self.snp_path
    
    def set_txs(self, vhigh, t_rise, ui, res_tx, cap_tx):
        self.ui = ui
        for pid in self.tx_ports:
            self.txs.append(Tx(pid, vhigh, t_rise, ui, res_tx, cap_tx))
        
        for pid_pos, pid_neg in self.tx_diff_ports:
            self.txs.append(Tx_diff(pid_pos, pid_neg, vhigh, t_rise, ui, res_tx, cap_tx))
            
    def set_rxs(self, res_rx, cap_rx):
        for pid in self.rx_ports:
            self.rxs.append(Rx(pid, res_rx, cap_rx))

        for pid_pos, pid_neg in self.rx_diff_ports:
            self.rxs.append(Rx_diff(pid_pos, pid_neg, res_rx, cap_rx))

    def _ports_for_tx(self, tx):
        if isinstance(tx, Tx):
            return [tx.pid]
        if isinstance(tx, Tx_diff):
            return [tx.pid_pos, tx.pid_neg]
        raise TypeError(f'Unsupported transmitter type: {type(tx)}')

    def _ports_for_rx(self, rx):
        if isinstance(rx, Rx):
            return [rx.pid]
        if isinstance(rx, Rx_diff):
            return [rx.pid_pos, rx.pid_neg]
        raise TypeError(f'Unsupported receiver type: {type(rx)}')

    def _collect_coupled_ports(self, source_ports, threshold_db):
        if threshold_db is None:
            return list(self.all_ports)

        strong = set(source_ports)
        for src in source_ports:
            src_idx = src - 1
            for m_idx in range(self.total_ports):
                port_id = m_idx + 1
                if port_id in strong:
                    continue
                coupling = np.abs(self.network.s[:, m_idx, src_idx])
                if coupling.size == 0:
                    continue
                peak = float(np.max(coupling))
                if peak <= 0.0:
                    db_value = float('-inf')
                else:
                    db_value = 20.0 * np.log10(peak)
                if db_value >= threshold_db:
                    strong.add(port_id)

        expanded = set()
        for port in strong:
            expanded.update(self._port_pair_map.get(port, {port}))
        return sorted(expanded)

    def _ensure_reduced_network(self, port_ids):
        key = tuple(port_ids)
        if key in self._reduced_cache:
            return self._reduced_cache[key]

        port_indexes = [pid - 1 for pid in port_ids]
        reduced = self.network.subnetwork(port_indexes)
        basename = os.path.join(self._temp_dir, f'reduced_{"_".join(str(pid) for pid in port_ids)}')
        reduced.write_touchstone(basename)
        touchstone_path = os.path.abspath(f'{basename}.s{len(port_ids)}p').replace('\\', '/')
        self._reduced_cache[key] = touchstone_path
        return touchstone_path

    def _build_channel_block(self, touchstone_path, port_ids):
        nets = ' '.join(f'net_{pid}' for pid in port_ids)
        return [
            f'.model "Channel" S TSTONEFILE="{touchstone_path}" {self._channel_options}',
            f'S1 {nets} FQMODEL="Channel"'
        ]

    
    
    def run(self, tstep='100ps', tstop='3ns', threshold_db=-40.0):
        try:
            threshold_value = float(threshold_db)
        except (TypeError, ValueError):
            threshold_value = None if threshold_db is None else -40.0

        for rx in self.rxs:
            rx.waveforms.clear()

        design = Design(tstep, tstop, self.aedt_version)

        for tx1 in self.txs:
            source_ports = self._ports_for_tx(tx1)
            if threshold_value is None:
                coupled_ports = list(self.all_ports)
            else:
                coupled_ports = self._collect_coupled_ports(source_ports, threshold_value)
            if not coupled_ports:
                continue

            # Guarantee the driven ports are retained even if numerical issues trimmed them.
            missing_sources = [pid for pid in source_ports if pid not in coupled_ports]
            if missing_sources:
                coupled_ports = sorted(set(coupled_ports).union(source_ports))

            reduced_touchstone = self._ensure_reduced_network(coupled_ports)
            netlist = self._build_channel_block(reduced_touchstone, coupled_ports)

            active_receivers = []

            for tx2 in self.txs:
                tx_ports = self._ports_for_tx(tx2)
                if any(pid not in coupled_ports for pid in tx_ports):
                    continue
                netlist += tx2.get_netlist(tx2 is tx1)

            for rx in self.rxs:
                rx_ports = self._ports_for_rx(rx)
                if any(pid not in coupled_ports for pid in rx_ports):
                    continue
                netlist += rx.get_netlist()
                active_receivers.append(rx)

            if not active_receivers:
                # No receivers with meaningful coupling; skip transient analysis.
                continue

            result = design.run('\n'.join(netlist))

            for rx in active_receivers:
                if isinstance(rx, Rx):
                    waveform = result.get(rx.pid)
                    if waveform:
                        rx.waveforms[tx1] = waveform
                    continue

                if isinstance(rx, Rx_diff):
                    pos = result.get(rx.pid_pos)
                    neg = result.get(rx.pid_neg)
                    if pos and neg:
                        time, waveform_pos = pos
                        _, waveform_neg = neg
                        combined = (time, [vpos - vneg for vpos, vneg in zip(waveform_pos, waveform_neg)])
                        rx.waveforms[tx1] = combined
            
    def calculate(self, output_path):
        ui = float(self.ui.replace('ps', '')) 
        
        processed_rxs = []
        for rx in self.rxs:
            if not rx.waveforms:
                continue
            data = []
            for tx, (time, voltage) in rx.waveforms.items():
                data.append((max(voltage), tx))
            _, tx = sorted(data)[-1]
            rx.tx = tx
            processed_rxs.append(rx)

        result = []
        for rx in processed_rxs:
            xtalk = 0
            sig = 0.0
            isi = 0.0
            for tx, waveform in rx.waveforms.items():
                time, voltage = waveform 
                if tx == rx.tx: 
                    sig, isi = get_sig_isi(time, voltage, ui)
                    continue
                
                xtalk += integrate_nonuniform(time, [abs(v) for v in voltage])
            pseudo_eye = sig - isi - xtalk
            denom = isi + xtalk
            if denom == 0:
                p_ratio = float('inf') if sig > 0 else 0.0
            else:
                p_ratio = sig / denom
            
            if isinstance(rx, Rx):
                tx_id = self.port_name_map.get(rx.tx.pid, str(rx.tx.pid))
                rx_id = self.port_name_map.get(rx.pid, str(rx.pid))
            elif isinstance(rx, Rx_diff): 
                tx_pos = self.port_name_map.get(rx.tx.pid_pos, str(rx.tx.pid_pos))
                tx_neg = self.port_name_map.get(rx.tx.pid_neg, str(rx.tx.pid_neg))
                rx_pos = self.port_name_map.get(rx.pid_pos, str(rx.pid_pos))
                rx_neg = self.port_name_map.get(rx.pid_neg, str(rx.pid_neg))
                tx_id = f'{tx_pos}/{tx_neg}'
                rx_id = f'{rx_pos}/{rx_neg}'
            
            result.append(f'{tx_id:5}, {rx_id:5}, {sig:10.3f}, {isi:10.3f}, {xtalk:10.3f}, {pseudo_eye:10.3f}, {p_ratio:10.3f}')
            
        with open(output_path, 'w') as f:
            f.writelines('tx_id, rx_id, sig(V*ps), isi(V*ps), xtalk(V*ps), pseudo_eye(V*ps), power_ratio\n')
            f.write('\n'.join(result))                

    
    
if __name__ == '__main__':
    with open(project_path) as f:
        info = json.load(f)
    wkdir = os.path.dirname(project_path)
    
    config = load_configuration(project_path)
    params = build_cct_parameters(config['cct_settings'])

    cct = CCT(
        config['touchstone_path'],
        tx_ports=config['tx_ports'],
        rx_ports=config['rx_ports'],
        tx_diff_ports=config['tx_diff_ports'],
        rx_diff_ports=config['rx_diff_ports'],
        port_name_map=config['port_name_map'],
        aedt_version=params['aedt_version']
    )

    cct.set_txs(
        vhigh=params['vhigh'],
        t_rise=params['t_rise'],
        ui=params['unit_interval'],
        res_tx=params['res_tx'],
        cap_tx=params['cap_tx']
    )
    cct.set_rxs(
        res_rx=params['res_rx'],
        cap_rx=params['cap_rx']
    )
    cct.run(
        tstep=params['tstep'],
        tstop=params['tstop'],
        threshold_db=params['sparam_threshold_db']
    )
    
    

    cct_path = os.path.join(wkdir, 'cct.csv')
    
    cct.calculate(output_path=cct_path)
    info['cct_path'] = cct_path
    with open(project_path, 'w') as f:
        json.dump(info, f, indent=3)
