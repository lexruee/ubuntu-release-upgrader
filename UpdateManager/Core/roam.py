# utils.py 
#  
#  Copyright (c) 2011 Canonical
#  
#  Author:  Alex Chiang <achiang@canonical.com>
#           Michael Vogt <michael.vogt@ubuntu.com>
# 
#  This program is free software; you can redistribute it and/or 
#  modify it under the terms of the GNU General Public License as 
#  published by the Free Software Foundation; either version 2 of the
#  License, or (at your option) any later version.
# 
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
# 
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
#  USA


import dbus

class ModemManagerHelper(object):

    # data taken from 
    #  http://projects.gnome.org/NetworkManager/developers/mm-spec-04.html
    MM_DBUS_IFACE = "org.freedesktop.ModemManager"
    MM_DBUS_IFACE_MODEM = MM_DBUS_IFACE + ".Modem"

    # GSM
    # Not registered, not searching for new operator to register. 
    MM_MODEM_GSM_NETWORK_REG_STATUS_IDLE = 0
    # Registered on home network. 
    MM_MODEM_GSM_NETWORK_REG_STATUS_HOME = 1
    # Not registered, searching for new operator to register with. 
    MM_MODEM_GSM_NETWORK_REG_STATUS_SEARCHING = 2
    # Registration denied. 
    MM_MODEM_GSM_NETWORK_REG_STATUS_DENIED = 3
    # Unknown registration status. 
    MM_MODEM_GSM_NETWORK_REG_STATUS_UNKNOWN = 4
    # Registered on a roaming network. 
    MM_MODEM_GSM_NETWORK_REG_STATUS_ROAMING = 5

    # CDMA
    # Registration status is unknown or the device is not registered.
    MM_MODEM_CDMA_REGISTRATION_STATE_UNKNOWN = 0
    # Registered, but roaming status is unknown or cannot be provided 
    # by the device. The device may or may not be roaming.
    MM_MODEM_CDMA_REGISTRATION_STATE_REGISTERED = 1
    #     Currently registered on the home network.
    MM_MODEM_CDMA_REGISTRATION_STATE_HOME = 2
    #     Currently registered on a roaming network.
    MM_MODEM_CDMA_REGISTRATION_STATE_ROAMING = 3

    def __init__(self):
        self.bus = dbus.SystemBus()
        self.proxy = self.bus.get_object("org.freedesktop.ModemManager", 
                                         "/org/freedesktop/ModemManager")
        modem_manager = dbus.Interface(self.proxy, self.MM_DBUS_IFACE)
        self.modems = modem_manager.EnumerateDevices()

    def is_gsm_roaming(self):
        for m in self.modems:
            dev = self.bus.get_object(self.MM_DBUS_IFACE, m)
            net = dbus.Interface(dev, self.MM_DBUS_IFACE_MODEM + ".Gsm.Network")
            reg = net.GetRegistrationInfo()
            # Be conservative about roaming. If registration unknown, 
            # assume yes.
            # MM_MODEM_GSM_NETWORK_REG_STATUS
            if reg[0] in (self.MM_MODEM_GSM_NETWORK_REG_STATUS_UNKNOWN,
                          self.MM_MODEM_GSM_NETWORK_REG_STATUS_ROAMING):
                return True
            return False

    def is_cdma_roaming(self):
        for m in self.modems:
            dev = self.bus.get_object(self.MM_DBUS_IFACE, m)
            cdma = bus.Interface(dev, self.MM_DBUS_IFACE_MODEM + ".Cdma")
            (cmda_1x, evdo) = cdma.GetRegistrationState()
            # Be conservative about roaming. If registration unknown, 
            # assume yes.
            # MM_MODEM_CDMA_REGISTRATION_STATE
            roaming_states (self.MM_MODEM_CDMA_REGISTRATION_STATE_REGISTERED,
                            self.MM_MODEM_CDMA_REGISTRATION_STATE_ROAMING) 
            if cmda_1x in roaming_states:
                return True
            elif evdo in roaming_states:
                return True
            return False

class NetworkManagerHelper(object):
    NM_DBUS_IFACE = "org.freedesktop.NetworkManager"

    # The device type is unknown. 
    NM_DEVICE_TYPE_UNKNOWN = 0
    # The device is wired Ethernet device. 
    NM_DEVICE_TYPE_ETHERNET = 1
    # The device is an 802.11 WiFi device. 
    NM_DEVICE_TYPE_WIFI = 2
    # The device is a GSM-based cellular WAN device. 
    NM_DEVICE_TYPE_GSM = 3
    # The device is a CDMA/IS-95-based cellular WAN device. 
    NM_DEVICE_TYPE_CDMA = 4

    def __init__(self):
        self.bus = dbus.SystemBus()
        self.proxy = self.bus.get_object("org.freedesktop.NetworkManager", 
                                         "/org/freedesktop/NetworkManager")

    def is_active_connection_gsm_or_cdma_roaming(self):
        res = False
        nm = dbus.Interface(self.proxy, "org.freedesktop.NetworkManager")
        props = dbus.Interface(self.proxy, "org.freedesktop.DBus.Properties")
        actives = props.Get(self.NM_DBUS_IFACE, 'ActiveConnections')
        for a in actives:
            active = self.bus.get_object(self.NM_DBUS_IFACE, a)
            props = dbus.Interface(active, "org.freedesktop.DBus.Properties")
            default = props.Get(self.NM_DBUS_IFACE + ".Connection.Active", 
                                'Default')
            if default != 1:
                continue
    

            devs = props.Get(self.NM_DBUS_IFACE + ".Connection.Active", 
                             'Devices')
            for d in devs:
                dev = self.bus.get_object(self.NM_DBUS_IFACE, d)
                props = dbus.Interface(dev, "org.freedesktop.DBus.Properties")
                type = props.Get(self.NM_DBUS_IFACE + ".Device", 'DeviceType')
                if type == self.NM_DEVICE_TYPE_GSM:
                    mmhelper = ModemManagerHelper()
                    res |= mmhelper.is_gsm_roaming()
                elif type == self.NM_DEVICE_TYPE_CDMA:
                    mmhelper = ModemManagerHelper()
                    res |= mmhelper.is_cdma_roaming()
                else:
                    continue
        return res

if __name__ == "__main__":
    
    # test code
    mmhelper = ModemManagerHelper()
    print mmhelper.modems
    mmhelper.is_gsm_roaming()
    mmhelper.is_cdma_roaming()

    # roaming?
    nmhelper = NetworkManagerHelper()
    print "roam: ", nmhelper.is_active_connection_gsm_or_cdma_roaming()