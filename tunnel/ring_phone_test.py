from xband_config import my_ip
from xband_config import opponent_ip
from xband_config import cpu_id_spoof
from xband_config import opponent_port
from xband_config import opponent_id
from xband_config import local_port
import sip_ring

opponent = opponent_ip
sip = sip_ring.SIP('user','',opponent,opponent_port,local_ip = my_ip,local_port=local_port)
sip.call(opponent_id,3)
