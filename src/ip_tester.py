import re
import json
import base64
import hashlib
import asyncio
import requests
import websockets
import logging
from pathlib import Path
from datetime import datetime
import random
from typing import Dict, List

class IPTester:
   def __init__(self, config: Dict):
       self.config = config
       self.setup_logging()
       self.session = requests.Session()
       
       self.NODE_IDS = {
           'TELECOM': [
               '1227', '1312', '1169', '1135', '1310', 
               '1132', '1214', '1311', '1138', '1304'
           ],
           'UNICOM': [
               '1254', '1275', '1278', '1264', '1273', 
               '1266', '1276', '1277', '1253', '1226'
           ],
           'MOBILE': [
               '1249', '1237', '1290', '1294', '1250', 
               '1295', '1287', '1242', '1245', '1283'
           ],
           'OVERSEAS': [
               '1340',  # 香港 BGP
               '1341',  # 新加坡
               '1343',  # 日本东京
               '1345'   # 美国洛杉矶
           ]
       }

       self.results_dir = Path(self.config.get('results_dir', 'results'))
       self.results_dir.mkdir(exist_ok=True)

   def setup_logging(self):
       log_dir = Path('logs')
       log_dir.mkdir(exist_ok=True)
       
       logging.basicConfig(
           level=logging.INFO,
           format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
           handlers=[
               logging.FileHandler(log_dir / f'ip_tester_{datetime.now():%Y%m%d}.log'),
               logging.StreamHandler()
           ]
       )
       self.logger = logging.getLogger('IPTester')

   def _x(self, input_str: str, key: str) -> str:
       key = key + "PTNo2n3Ev5"
       output = ""
       for i, char in enumerate(input_str):
           char_code = ord(char) ^ ord(key[i % len(key)])
           output += chr(char_code)
       return output

   def _set_ret(self, guard_cookie: str) -> str:
       prefix = guard_cookie[:8]
       num = int(guard_cookie[12:]) if len(guard_cookie) > 12 else 0
       val = num * 2 + 18 - 2
       encrypted = self._x(str(val), prefix)
       return base64.b64encode(encrypted.encode()).decode()

   async def test_single_ip(self, ip: str, node_id: str, max_retries: int = 3) -> Dict:
        for retry in range(max_retries):
            try:
                headers = {
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'accept-language': 'zh-CN,zh;q=0.9',
                    'content-type': 'application/x-www-form-urlencoded',
                    'origin': 'https://www.itdog.cn',
                    'referer': 'https://www.itdog.cn/batch_ping/',
                    'user-agent': 'Mozilla/5.0'
                }

                # 首先访问主页
                response = self.session.get('https://www.itdog.cn/batch_ping/', headers=headers)
                await asyncio.sleep(1)

                data = {
                    'host': ip,
                    'node_id': node_id,
                    'check_mode': 'ping'  # 改成ping模式
                }

                # 获取cookie
                response = self.session.post('https://www.itdog.cn/batch_ping/', headers=headers, data=data)
                if 'guard' in self.session.cookies:
                    guardret = self._set_ret(self.session.cookies['guard'])
                    self.session.cookies.set('guardret', guardret)

                # 第二次POST
                response = self.session.post('https://www.itdog.cn/batch_ping/', headers=headers, data=data)
                content = response.text

                wss_match = re.search(r"""var wss_url='(.*)';""", content)
                task_match = re.search(r"""var task_id='(.*)';""", content)

                if not wss_match or not task_match:
                    raise ValueError("无法获取WebSocket信息")

                wss_url = wss_match.group(1)
                task_id = task_match.group(1)
                task_token = hashlib.md5((task_id + "token_20230313000136kwyktxb0tgspm00yo5").encode()).hexdigest()[8:-8]

                async with websockets.connect(wss_url) as ws:
                    await ws.send(json.dumps({
                        "task_id": task_id,
                        "task_token": task_token
                    }))

                    while True:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=3)
                            data = json.loads(msg)

                            if 'result' in data:
                                latency = float(data.get('result', 0))
                                if latency > 0:
                                    return {
                                        'latency': latency,
                                        'loss': 0,
                                        'available': True,
                                        'node_id': node_id
                                    }

                            if data.get('type') == 'finished':
                                break

                        except asyncio.TimeoutError:
                            break

            except Exception as e:
                if retry < max_retries - 1:
                    self.logger.warning(f"重试第 {retry + 1} 次测试 IP {ip}")
                    await asyncio.sleep(1)
                    continue
                self.logger.error(f"测试 IP {ip} 出错: {str(e)}")

        return {
            'latency': float('inf'),
            'loss': 100,
            'available': False,
            'node_id': node_id
        }

   async def test_ip(self, ip: str) -> Dict:
       results = {
           'ip': ip,
           'status': 'ok', 
           'tests': {}
       }

       # 为每个运营商随机选择节点
       test_nodes = self.get_test_nodes(ip)

       for isp, nodes in test_nodes.items():
           for node_id in nodes:
               try:
                   self.logger.info(f"Testing IP {ip} with {isp} node {node_id}")
                   test_result = await self.test_single_ip(ip, node_id)
                   
                   if isp == 'OVERSEAS' and test_result.get('available', False):
                       results['tests'][isp] = test_result
                       return results
                       
                   if isp not in results['tests'] or \
                      (results['tests'][isp].get('latency', float('inf')) > test_result.get('latency', float('inf'))):
                       results['tests'][isp] = test_result

               except Exception as e:
                   self.logger.error(f"Error testing {ip} with node {node_id}: {str(e)}")
                   if isp not in results['tests']:
                       results['tests'][isp] = {
                           'latency': float('inf'),
                           'loss': 100,
                           'available': False
                       }
                       
           await asyncio.sleep(1)

       return results

   def get_test_nodes(self, ip: str) -> Dict[str, List[str]]:
       is_overseas = self.config.get('overseas_mode', False)
       
       if is_overseas:
           return {
               'OVERSEAS': random.sample(self.NODE_IDS['OVERSEAS'], 
                                     k=min(2, len(self.NODE_IDS['OVERSEAS'])))
           }
       
       nodes = {}
       for isp in ['TELECOM', 'UNICOM', 'MOBILE']:
           nodes[isp] = [random.choice(self.NODE_IDS[isp])]
       return nodes

   async def test_batch(self, ip_list: List[str]) -> List[Dict]:
       results = []
       for i, ip in enumerate(ip_list):
           self.logger.info(f"Testing IP {i+1}/{len(ip_list)}: {ip}")
           try:
               result = await self.test_ip(ip)
               results.append(result)
               
               if (i + 1) % 10 == 0:
                   self.save_intermediate_results(results)
                   await asyncio.sleep(2)
               else:
                   await asyncio.sleep(1)
                   
           except Exception as e:
               self.logger.error(f"Error testing IP {ip}: {str(e)}")
       
       return results

   def save_intermediate_results(self, results: List[Dict]):
       try:
           timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
           result_file = self.results_dir / f'test_results_intermediate_{timestamp}.json'
           
           with open(result_file, 'w') as f:
               json.dump(results, f, indent=2)
               
           self.logger.info(f"Saved intermediate results to {result_file}")
           
       except Exception as e:
           self.logger.error(f"Error saving intermediate results: {str(e)}")

   def start(self, ip_list: List[str]) -> List[Dict]:
    loop = asyncio.get_event_loop()
    # 改为 run_until_complete 而不是 asyncio.run
    results = loop.run_until_complete(self.test_batch(ip_list))
    
    # 保存结果到文件
    if results:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        result_file = self.results_dir / f'test_results_{timestamp}.json'
        with open(result_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        # 打印测试结果
        for result in results:
            self.logger.info(f"IP: {result['ip']} 测试结果:")
            for isp, data in result['tests'].items():
                if data['available']:
                    self.logger.info(f"  {isp}: 延迟 {data['latency']}ms")
                else:
                    self.logger.info(f"  {isp}: 不可用")
    
    return results