"""
<plugin key="Marstek_modbus"
        name="Marstek Venus Modbus"
        author="SilentSimon"
        version="1.0">

    <params>
        <param field="Address" label="Gateway IP Address" width="200px" required="true"/>
        <param field="Port" label="TCP Port" width="60px" default="502"/>
        <param field="Mode1" label="Modbus Slave ID" width="60px" default="1"/>
        <param field="Mode6" label="Poll interval (seconds)" width="75px" default="30"/>
    </params>
</plugin>
"""

import Domoticz
from pymodbus.client import ModbusTcpClient

MODE_NAMES = {0:"Manual",1:"Anti-feed",2:"Trade"}
MODE_LEVELS = {0:0,1:10,2:20}
LEVEL_TO_MODE = {0:0,10:1,20:2}

class BasePlugin:

    def __init__(self):
        self.counter = 0

    def onStart(self):

        defs = [
            (1,"SOC","Percentage"),
            (2,"Remaining Energy","kWh"),
            (3,"Battery Voltage","Voltage"),
            (4,"Battery Current","CustomA"),
            (5,"Battery Power","Usage"),
            (6,"Battery Temperature","Temperature"),
            (7,"Current Mode","Text"),
            (8,"Mode Selector","Selector"),
            (9,"Battery Capacity","kWh"),
            (10,"AC Power","Usage"),
            (11,"Connection Status","Text"),
            (12,"RS485 Control Status","Text"),
            (13,"Cycle Count","Custom"),
            (14,"Battery Efficiency","Percentage"),
            (15,"Charge/Discharge Direction","Text"),
            (16,"Estimated SOH","Percentage"),
            (17,"Internal Temperature","Temperature"),
            (18,"MOS1 Temperature","Temperature"),
            (19,"MOS2 Temperature","Temperature"),
            (20,"Max Cell Voltage","Voltage"),
            (21,"Min Cell Voltage","Voltage"),
            (22,"Daily Charge Energy","kWh"),
            (23,"Daily Discharge Energy","kWh"),
        ]

        for unit,name,typ in defs:
            if unit in Devices:
                continue

            if typ == "Text":
                Domoticz.Device(Name=name,Unit=unit,Type=243,Subtype=19).Create()
            elif typ == "Selector":
                Domoticz.Device(Name=name,Unit=unit,TypeName="Selector Switch",
                                Options={"LevelActions":"|||",
                                         "LevelNames":"Manual|Anti-feed|Trade",
                                         "LevelOffHidden":"false",
                                         "SelectorStyle":"0"}).Create()
            elif typ == "CustomA":
                Domoticz.Device(Name=name,Unit=unit,Type=243,Subtype=31,
                                Options={"Custom":"A"}).Create()
            elif typ == "Custom":
                Domoticz.Device(Name=name,Unit=unit,Type=243,Subtype=31).Create()
            elif typ == "kWh":
                Domoticz.Device(Name=name,Unit=unit,Type=113,Subtype=0).Create()
            elif typ == "Percentage":
                Domoticz.Device(Name=name,Unit=unit,TypeName="Percentage").Create()
            else:
                Domoticz.Device(Name=name,Unit=unit,TypeName=typ).Create()

        Domoticz.Heartbeat(10)

    def client(self):
        return ModbusTcpClient(Parameters["Address"], port=int(Parameters["Port"]))

    def read_u16(self,c,r):
        return c.read_holding_registers(address=r,count=1,device_id=int(Parameters["Mode1"])).registers[0]

    def read_s16(self,c,r):
        v=self.read_u16(c,r)
        return v-65536 if v>32767 else v

    def read_u32(self,c,r):
        rr=c.read_holding_registers(address=r,count=2,device_id=int(Parameters["Mode1"]))
        return (rr.registers[0] << 16) | rr.registers[1]

    def onCommand(self, Unit, Command, Level, Hue):
        if Unit != 8:
            return
        c=self.client()
        if not c.connect():
            return
        try:
            c.write_register(address=43000,value=LEVEL_TO_MODE.get(Level,0),
                             device_id=int(Parameters["Mode1"]))
        finally:
            c.close()

    def onHeartbeat(self):
        self.counter += 10
        interval=max(10,int(Parameters["Mode6"] or 30))
        if self.counter < interval:
            return
        self.counter=0

        c=self.client()
        if not c.connect():
            Devices[11].Update(0,"Disconnected")
            return

        try:
            Devices[11].Update(0,"Connected")

            soc=self.read_u16(c,34002)/10.0
            capacity=self.read_u16(c,32105)*0.001
            remaining=capacity*soc/100.0

            voltage=self.read_u16(c,30100)/100.0
            current=self.read_s16(c,30101)/10.0
            battery_power=self.read_s16(c,30001)

            temp=self.read_s16(c,35000)/10.0
            mos1=self.read_s16(c,35001)/10.0
            mos2=self.read_s16(c,35002)/10.0

            mode=self.read_u16(c,43000)
            ac_power=self.read_s16(c,30006)

            rs485=self.read_u16(c,42000)
            cycle_count=self.read_u16(c,34003)

            max_cell=self.read_u16(c,37007)/1000.0
            min_cell=self.read_u16(c,37008)/1000.0

            daily_charge=self.read_u32(c,33004)*0.01
            daily_discharge=self.read_u32(c,33006)*0.01

            eff=round(abs(ac_power)/abs(battery_power)*100,1) if abs(battery_power)>50 else 0

            # inverted as requested
            if battery_power < -50:
                direction="Discharging"
            elif battery_power > 50:
                direction="Charging"
            else:
                direction="Idle"

            rs485_status="Enabled" if rs485==21930 else ("Disabled" if rs485==21947 else str(rs485))

            soh=100.0

            Devices[1].Update(0,str(round(soc,1)))
            remaining_wh = int(round(remaining * 1000))
            Devices[2].Update(remaining_wh, str(remaining_wh))
            Devices[3].Update(0,str(round(voltage,2)))
            Devices[4].Update(0,str(round(current,1)))
            Devices[5].Update(0,str(battery_power))
            Devices[6].Update(0,str(round(temp,1)))
            Devices[7].Update(0,MODE_NAMES.get(mode,str(mode)))
            Devices[8].Update(nValue=1,sValue=str(MODE_LEVELS.get(mode,0)))
            capacity_wh = int(round(capacity * 1000))
            Devices[9].Update(capacity_wh, str(capacity_wh))
            Devices[10].Update(0,str(ac_power))
            Devices[12].Update(0,rs485_status)
            Devices[13].Update(0,str(cycle_count))
            Devices[14].Update(0,str(eff))
            Devices[15].Update(0,direction)
            Devices[16].Update(0,str(soh))
            Devices[17].Update(0,str(round(temp,1)))
            Devices[18].Update(0,str(round(mos1,1)))
            Devices[19].Update(0,str(round(mos2,1)))
            Devices[20].Update(0,str(round(max_cell,3)))
            Devices[21].Update(0,str(round(min_cell,3)))
            daily_charge_wh = int(round(daily_charge * 1000))
            daily_discharge_wh = int(round(daily_discharge * 1000))
            Devices[22].Update(daily_charge_wh, str(daily_charge_wh))
            Devices[23].Update(daily_discharge_wh, str(daily_discharge_wh))
        except Exception as e:
            Domoticz.Error("Marstek Modbus: {}".format(e))
        finally:
            c.close()

global _plugin
_plugin=BasePlugin()

def onStart(): _plugin.onStart()
def onHeartbeat(): _plugin.onHeartbeat()
def onCommand(Unit, Command, Level, Hue): _plugin.onCommand(Unit, Command, Level, Hue)
