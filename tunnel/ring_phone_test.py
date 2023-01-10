from xband_config import my_ip
from xband_config import opponent_port
from xband_config import opponent_id
import femtosip.femtosip as sip_ring

opponent = opponent_ip
sip = sip_ring.SIP('user','',opponent,opponent_port,local_ip = my_ip,protocol="udp")
sip.call(opponent_id,3)
