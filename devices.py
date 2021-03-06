from abc import abstractmethod, ABCMeta
from collections import deque
from logger import Logger
from event import EventHook
from util import bin_hex, mult_x, INIT_FRAME_BIT, get_device_port
from ip import IP
from payload import PayLoad

class Network_Component(metaclass=ABCMeta):
    def __init__(self,name,no_ports):
        # name of device
        self.name=name
        # list of ports, if ports[i] = '' then this ports is not connected, else this ports is connected to ports[i]
        self.ports=['' for x in range(no_ports)]

    @abstractmethod
    def clean(self):
        pass

class Wire(Network_Component):
    def __init__(self,name,port_1,port_2):
        super().__init__(name,2)
        # port 1 that a wire connect
        self.ports[0]=port_1
        # port 2 
        self.ports[1]=port_2

        # bit of the wire
        self.red=None
        # bit of the wire
        self.blue=None

    def clean(self):
        self.red = None
        self.blue = None

class Device(Network_Component,metaclass=ABCMeta):
    ''' Abstract class that represent a device on the network'''
    def __init__(self,name,no_ports):
        super().__init__(name,no_ports)
        # values that read
        self.read_value = [None for i in range(no_ports)]
        # cable to send True=red False=blue
        self.cable_send=[False for i in range(no_ports)]
        # device's log file
        self.logger = Logger(self.name + ".txt")
        # event to ask for the signal time of the simulation.
        self.askSignalTime = EventHook()
        # event to query a specific device from the device list
        
        self.consultDevice = EventHook()
        # event to consult the index of a device given its name
        self.consultDeviceMap = EventHook()
        # event to know the number of devices at a given time on the network
        self.askCountDevice = EventHook()

    def report_receive_ok(self, bit, port):
        ''' Report by a log message that it received a bit successfully '''
        # If the bit is None then it does not report because there was no current in the communication channel 
        if bit == None:
            return
        # the logger write the log message
        self.logger.write(f"{port} receive {bit}")

    def clean(self):
        self.read_value = [None for i in range(len(self.ports))]
        
    def xor(self, a, b):
        ''' XOR operator to apply to the channel and review if another device is sending data '''
        if a==None:
            return b
        elif b==None:
            return a
        return a^b

class Host(Device, IP, PayLoad):
    ''' This class represent a Host device '''
    def __init__(self,name, no_ports = 1):
        Device.__init__(self,name,no_ports)
        IP.__init__(self)
        PayLoad.__init__(self, name)
        self.data_logger = Logger(self.name + "_data.txt")
        self.check_size = lambda x, l : len(x) >= l
        self.clean_receive()
        self.clean_sending()
        self.set_MAC("")
        # * Error Detection and correction
        self.detection = None
        
        # * ARP Protocol fields
        self.doing_ARPQ = False
            # * The representation of 'ARPQ' on ASCII is:
            # * A = 41
            # * R = 52
            # * P = 50
            # * Q = 51
        self.ARPQ_rep = "41525051"
        
    def construct_ARPQ_frame(self, ip):
        """
            Construct a frame to send ARPQ

            MAC to FFFF
            MAC origin 
            ARPQ
            IP
        """
        return "FFFF" + ' ' + self.ARPQ_rep +  ip

    def transition_receive(self):
        self.receiving = (self.receiving + 1) % 7

    def clean_receive(self):
        self.receiving = 0
        self.receive_MAC_1 = ""
        self.receive_MAC_2 = ""
        self.receive_size = ""
        self.receive_off = ""
        self.receive_data = ""
        self.receive_time = 0
        self.receive_detect = ""

    def clean_sending(self):
        self.data_to_send = ""
        self.index_sending = 0
        self.time_sending = 0
        self.sending_frame = None

    def report_collision(self, data):
        ''' Report collision on log file '''
        self.logger.write(f"{self.name} send {data} collision")
    
    def report_send_ok(self, data):
        ''' Report success send of log file '''
        if data == None:
            return
        self.logger.write(f"{self.name}_1 send {data} ok")

    def send(self, data, frame=False):
        ''' Function to send data to the network '''

        if not self.data_to_send == "":
            return False
        # data to send
        self.data_to_send = data
        # index of the bit in data to send
        self.index_sending = 0
        # time sending data[index]
        self.time_sending = 0

        self.sending_frame = frame
        can_send = self._send(self.data_to_send[self.index_sending])
        if not can_send:
            self.clean_sending()
        return can_send

    def _send(self, bit):
        if self.ports[0] is "":
            self.report_send_ok(bit)
            return True
        wire = self.consultDevice.fire(self.consultDeviceMap.fire(get_device_port(self.ports[0])[0])) 
        
        if self.cable_send[0]:
            wire.red = bit
        else:
            wire.blue = bit

        wd = self.consultDevice.fire(self.consultDeviceMap.fire(get_device_port(wire.ports[1])[0] if wire.ports[0]==self.name+"_" +str(1) else get_device_port(wire.ports[0])[0]))
        if isinstance(wd,Resender):
            wdp = wire.name+"_"+str(2) if wire.ports[0]==self.name+"_" +str(1) else wire.name+"_"+str(1)
            if wd.resend(bit, wdp) is "COLLISION":
                self.report_collision(bit)
                return False
            else:
                wd.resend(bit, wdp, True)
                wd.read_value[wd.ports.index(wdp)] = bit
        elif type(wd) is Host:
            wd.read_value[0] = bit
        self.report_send_ok(bit)
        return True

    def read(self, report):
        if self.ports[0] == "":
            return
        wire = self.consultDevice.fire(self.consultDeviceMap.fire(get_device_port(self.ports[0])[0])) 
        #rd = wire.red if not self.cable_send[0] else wire.blue
        rd = self.read_value[0]
        if report:
            self.report_receive_ok(rd, f"{self.name}_1")
            

            if self.receiving == 0 and rd == INIT_FRAME_BIT:
                self.transition_receive()
            elif self.receiving == 1:
                if rd == None:
                    return
                elif rd == INIT_FRAME_BIT:
                    self.clean_receive()
                    self.receiving = 1
                    return
                if self.receive_time == 0:
                    self.receive_MAC_1 += str(rd)
                if self.check_size(self.receive_MAC_1, 16):
                    if self.receive_MAC_1 == self.MAC or self.receive_MAC_1 == "1"*16:
                        self.transition_receive()
                    else:
                        self.receiving = 0
                        self.clean_receive()
            elif self.receiving == 2:
                if rd == None:
                    return
                elif rd == INIT_FRAME_BIT:
                    self.clean_receive()
                    self.receiving = 1
                    return
                if self.receive_time == 0:
                    self.receive_MAC_2 += str(rd)
                if self.check_size(self.receive_MAC_2, 16):
                    self.transition_receive()
            elif self.receiving == 3:
                if rd == None:
                    return
                elif rd == INIT_FRAME_BIT:
                    self.clean_receive()
                    self.receiving = 1
                    return
                if self.receive_time == 0:
                    self.receive_size += str(rd)
                if self.check_size(self.receive_size, 8):
                    self.transition_receive()
            elif self.receiving == 4:
                if rd == None:
                    return
                elif rd == INIT_FRAME_BIT:
                    self.clean_receive()
                    self.receiving = 1
                    return
                if self.receive_time == 0:
                    self.receive_off += str(rd)
                if self.check_size(self.receive_off, 8):
                    self.transition_receive()
            elif self.receiving == 5:
                if rd == None:
                    return
                elif rd == INIT_FRAME_BIT:
                    self.clean_receive()
                    self.receiving = 1
                    return
                if self.receive_time == 0:
                    self.receive_data += str(rd)
                if self.check_size(self.receive_data, 8*int(self.receive_size, 2)):
                    self.transition_receive()
            elif self.receiving == 6:
                if rd == None:
                    return
                elif rd == INIT_FRAME_BIT:
                    self.clean_receive()
                    self.receiving = 1
                    return
                if self.receive_time == 0:
                    self.receive_detect += str(rd)
                if self.check_size(self.receive_detect, 8*int(self.receive_off,2)):
                    detect = str()
                    if not self.detection.check("".join([INIT_FRAME_BIT, self.receive_MAC_1, self.receive_MAC_2, self.receive_size, self.receive_off, self.receive_data, self.receive_detect])):
                        detect += "ERROR"
                    self.data_logger.write(f"{bin_hex(self.receive_MAC_2)} {bin_hex(self.receive_data)} {detect}")
                    self.clean_receive()

            if self.receive_time < self.askSignalTime.fire() - 1:
                self.receive_time += 1
            else: 
                self.receive_time = 0   
    
    def keep_sending(self):
        ''' Keep sending a data throught network '''
        signal_time = self.askSignalTime.fire()
 
        # if this device is sending and the sending time is less that signal time then continue spreading data
        if self.time_sending < signal_time - 1:
            self._send(self.data_to_send[self.index_sending])
            self.time_sending += 1
            return True
        # if signal time is accomplished then
        else:
            # if send all data then spread "empty channel" status
            if self.index_sending >= len(self.data_to_send) - 1:
                self._send(None)
                self.clean_sending()
                return False
            # else spread the next bit 
            else:
                self.index_sending += 1
                self._send(self.data_to_send[self.index_sending])
                self.time_sending = 0
                return True

    def set_MAC(self,mac):
        self.MAC=mac

class Resender(Device,metaclass=ABCMeta):
    def __init__(self,name,no_ports):
        super().__init__(name,no_ports)
        self.internal_port_connection=['' for i in range(no_ports)]

    def resend(self,bit, port_name, write=False):
        pass

class Hub(Resender):
    ''' This class represent a Hub device '''
    def __init__(self,name,no_ports):
        super().__init__(name,no_ports)
    
    def report_resend(self, bit, port):
        ''' This function reports in the log messages the forwarding of data through all ports '''
        if bit == None:
            return
        name_ports = [self.name + "_" + str(i + 1) for i in range(len(self.ports))]
        name_ports.remove(port)
        for i in name_ports:
            self.logger.write(f"{i} send {bit}")
    
    def report_collision(self):
        pass

    def resend(self, bit, port_name, write=False):
        if write:
            self.read_value[self.ports.index(port_name)] = bit
        # lista de puertos por donde reenvio
        list_port = []

        # puerto del hub por donde recibio la info
        from_value = self.name + "_" + str(self.ports.index(port_name) + 1)

        # si hay que escribir el valor en el txt
        if write:
            self.report_receive_ok(bit,from_value )

        # por cada puerto reenvia
        for i in range(len(self.ports)):
            # toma el valor del puerto (esto es el puerto de un cable que esta conectado a ti)
            port = self.ports[i]

            # si el puerto es vacio o el puerto es por el mismo que recibes
            if port == "" or port == port_name:
                continue


            # dame el cable que esta conectado en el puerto
            wire = self.consultDevice.fire(self.consultDeviceMap.fire(get_device_port(port)[0]))

            # si envias por el rojo
            if self.cable_send[i]:
                # si el rojo no esta vacio entonces hay colision
                if not wire.red is None:
                    self.report_collision()
                    return "COLLISION"
                # si hay que escribir entonces pon el valor en el cable rojo
                if write:
                    wire.red = bit 
            else:
                # revisa si hay colision en el azul
                if not wire.blue is None:
                    self.report_collision()
                    return "COLLISION"
                # si hay que escribir entonces pon el valor en el cable azul
                if write:
                    wire.blue = bit 
                

            # agrega este indice a la lista
            list_port.append(i)
            
            # dispositivo con el que esta conectado a traves del cable
            wd = self.consultDevice.fire(self.consultDeviceMap.fire(get_device_port(wire.ports[1])[0] if wire.ports[0]==self.name+"_"+str(i+1)  else get_device_port(wire.ports[0])[0]))
            # si el dispositivo es un resender entonces dile que reenvie
            if isinstance(wd, Resender):
                # dame el puerto del cable que esta conectado al Resender
                wdp =wire.name+"_"+str(2) if wire.ports[0]==self.name+"_" +str(i+1) else wire.name+"_"+str(1)
                # revisa si el resender da colision
                if wd.resend(bit, wdp) is "COLLISION":
                    self.report_collision()
                    return "COLLISION"
                else:
                    # si no hubo colision entonces pon el valor
                    wd.resend(bit, wdp, True)
                    wd.read_value[wd.ports.index(wdp)] = bit
            elif type(wd) is Host:
                wd.read_value[0] = bit
        # reporta que renviaste si tienes que escribir
        if write:
            self.report_resend(bit, from_value)
        return list_port

class Switch(Resender):
    def __init__(self,name,no_ports):
        super().__init__(name,no_ports)
        # tablas de las MAC
        self.macs=[set(['1111111111111111']) for i in range(no_ports)]
        # cola de bits por cada puerto para enviar
        self.port_information=[deque() for i in range(no_ports)]
        # esta la mac de destino completa
        self.complete_mac=[False for i in range(no_ports)]
        # estados de la maquina de estados por puertos
        self.state=[0 for i in range(no_ports)]
        # mac de destino por cada puerto
        self.port_mac=['' for i in range(no_ports)]
        # mac de origen por cada puerto
        self.port_origin=['' for i in range(no_ports)]
        # time sending info must be minor than signal time
        self.time_sending = [0] * no_ports
        self.time_receiving = [0] * no_ports
    
    def clean_port(self, i):
        self.time_sending[i] = self.askSignalTime.fire()
        self.time_receiving[i] = 0
        self.state[i] = 0
        self.port_information[i] = deque()
        self.complete_mac[i] = False
        self.port_mac[i] = ""
        self.port_origin[i] = ""
        
    def refresh_time(self):
        st = self.askSignalTime.fire()
        self.time_sending = [st] * len(self.ports)

    def resend(self, bit, port_name, write=False):
        if write:
            # puerto del switch por donde recibio la info
            index_from = self.ports.index(port_name)
            from_value = self.name + "_" + str(index_from + 1)

            self.report_receive_ok(bit,from_value)

            if self.time_receiving[index_from] == self.askSignalTime.fire():
                self.time_receiving[index_from] = 0
            if self.time_receiving[index_from] == 0:
                self.port_information[index_from].append(bit)
            if self.time_receiving[index_from] <= self.askSignalTime.fire() -1:
                self.time_receiving[index_from] += 1
            

            if bit == INIT_FRAME_BIT:
                self.state[index_from]=1
            if len(self.port_information[index_from])==17 and self.state[index_from]==1:
                self.state[index_from]=2
                self.port_mac[index_from]=''.join(map(lambda x: str(x), [self.port_information[index_from][i] for i in range(1, len(self.port_information[index_from]))]))
            elif self.state[index_from]==2 and len(self.port_origin[index_from])<16:
                self.port_origin[index_from]+=bit
            
            if len(self.port_origin[index_from])==16:
                self.macs[index_from].add(self.port_origin[index_from])

    def send(self):
        for i in range(len(self.ports)):
            if len(self.port_information[i]) == 0:
                self.port_origin[i] = ""
                self.port_mac[i] = ""
                self.state[i]=0
                continue

            elif self.state[i]==1:
                continue
            empty = 0
            sent = False
            find=False
            for j in range(len(self.ports)):
                if self.port_mac[i] in self.macs[j]:
                    find=True
                    wire = self.consultDevice.fire(self.consultDeviceMap.fire(get_device_port(self.ports[j])[0]))
                    if wire is None:
                        self.macs[j].remove(self.port_mac[i])
                        continue
                    if self.cable_send[j]:
                        if wire.red is None:
                            wire.red= self.port_information[i][0]
                            sent = True
                    else:
                        if wire.blue is None:
                            wire.blue= self.port_information[i][0]
                            sent = True
                    if sent:
                        self.resend_bit(wire, i, j)
                    
            if not find:
                for j in range(len(self.ports)):
                    if self.ports[j] == "" or i == j:
                        empty += 1
                        continue
                    wire = self.consultDevice.fire(self.consultDeviceMap.fire(get_device_port(self.ports[j])[0]))
                    if wire is None:
                        continue
                    if self.cable_send[j]:
                        if wire.red is None:
                            wire.red=self.port_information[i][0]
                            sent = True
                    else:
                        if wire.blue is None:
                            wire.blue=self.port_information[i][0]   
                            sent = True
                    if sent:
                        self.resend_bit(wire, i, j)

            if sent or empty == len(self.ports):
                self.time_sending[i] -= 1
            if (empty == len(self.ports) or sent) and self.time_sending[i] == 0:
                self.port_information[i].popleft()
                self.time_sending[i] = self.askSignalTime.fire()

    def resend_bit(self, wire, i , j):
        bit = self.port_information[i][0]
        wd = self.consultDevice.fire(self.consultDeviceMap.fire(get_device_port(wire.ports[1])[0] if wire.ports[0]==self.name+"_"+str(j+1)  else get_device_port(wire.ports[0])[0]))
        # si el dispositivo es un resender entonces dile que reenvie
        if isinstance(wd, Resender):
            # dame el puerto del cable que esta conectado al Resender
            wdp =wire.name+"_"+str(2) if wire.ports[0]==self.name+"_" +str(j+1) else wire.name+"_"+str(1)
            # revisa si el resender da colision
            if wd.resend(bit, wdp) is "COLLISION":
                self.report_collision()
                return "COLLISION" 
            else:
                # si no hubo colision entonces pon el valor
                wd.resend(bit, wdp, True)
                wd.read_value[wd.ports.index(wdp)] = bit
        elif type(wd) is Host:
            wd.read_value[0] = bit

    def can_send(self, i):
        for j in range(len(self.ports)):
            if self.ports[j] == "" or i == j:
                continue
            wire = self.consultDevice.fire(self.consultDeviceMap.fire(get_device_port(self.ports[j])[0]))
            if self.cable_send[j]:
                if not wire.red is None:
                    return False
            else:
                if not wire.blue is None:
                    return False
        return True