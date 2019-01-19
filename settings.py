"""Settings."""

# Base URL of the Flow Manager endpoint
FMNGR_URL = 'http://localhost:8181/api/kytos/flow_manager/v2'

dpids = [
    '00:00:00:00:00:00:00:01', '00:00:00:00:00:00:00:02',
    '00:00:00:00:00:00:00:03', '00:00:00:00:00:00:00:04'
]

# kytos http server
http_server = "localhost"
# kytos http port
http_port = "8181"
# dvel endpoint
endpoint = "api/viniarck/dvel/changelane"
# influx db server
db_server = "localhost"
# influx db name
db_name = "dvel"

# frequency to eval the async loop
frequency = 0.5
# timeout to detect loss when sending requests to the db
timeout = 3
params = {"l_rtt_key": "d3", "max_rtt": 1.0e4}
# containers names and their respective lanes
containers = {
    "d3": {"rtt": 0.0, "pkt_loss": 0, "evc_path": 1},
    "d4": {"rtt": 0, "pkt_loss": 0.0, "evc_path": 2},
    "d5": {"rtt": 0.0, "pkt_loss": 0, "evc_path": 3},
}
