import argparse
import uvicorn
from .app import make_app

parser=argparse.ArgumentParser(description='Database-backed IT portal')
parser.add_argument('--host',default='0.0.0.0')
parser.add_argument('--port',type=int,default=8089)
args=parser.parse_args()
uvicorn.run(make_app(),host=args.host,port=args.port,access_log=False)
