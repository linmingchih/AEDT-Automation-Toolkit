
info = {}

info['xyz_path'] = "D:\\demo\\xyz.fld"
info['quantity_path'] = "D:\\demo\\quantity.fld"
info['solution'] = "Setup1 : LastAdaptive"
info['quantity'] = ["Mag_E"]
info['frequency'] = "5GHz"
info['phase'] = "0deg"

from pyaedt import Hfss

hfss = Hfss(version='2025.2')

oModule = hfss.ofieldsreporter

oModule.CalculatorWrite(
    info['xyz_path'],
    [
        "NAME:Write",
        ["NAME:Setup", "Solution:=", info['solution']],
        ["NAME:Expression", "Vector_Function:=", ["FuncValueX:=", "X", 
                                                  "FuncValueY:=", "Y", 
                                                  "FuncValueZ:=", "Z"]],
    ],
    ["Freq:=", info['frequency'], "Phase:=", info['phase']]
)

oModule.CalculatorWrite(
    info['quantity_path'],
    [
        "NAME:Write",
        ["NAME:Setup", "Solution:=", info['solution']],
        ["NAME:Expression", "NameOfExpression:=", info['quantity']],
    ],
    ["Freq:=", info['frequency'], "Phase:=", info['phase']]
)


#%%