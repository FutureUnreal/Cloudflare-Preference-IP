# ip_tester.py
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

from src.http_tester import HTTPTester

class IPTester:
    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger('IPTester')
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
        
        # 测试间隔控制
        self.test_interval = config.get('test_config', {}).get('test_interval', 1)

    async def start(self, ip_list: List[str]) -> List[Dict]:
        try:
            results = await self.test_batch(ip_list)
            return results
        except Exception as e:
            self.logger.error(f"测试过程发生错误: {str(e)}")
            raise

    async def test_batch(self, ip_list: List[str]) -> List[Dict]:
        results = []
        total = len(ip_list)
        
        for i, ip in enumerate(ip_list):
            try:
                self.logger.info(f"Testing IP {i+1}/{total}: {ip}")
                result = await self.test_ip(ip)
                results.append(result)
                
                # 每10个IP保存一次中间结果
                if (i + 1) % 10 == 0:
                    self.save_intermediate_results(results)
                    
                # 添加测试间隔
                await asyncio.sleep(self.test_interval)
                    
            except Exception as e:
                self.logger.error(f"Error testing IP {ip}: {str(e)}")
                results.append({
                    'ip': ip,
                    'status': 'error',
                    'error': str(e),
                    'tests': {}
                })
        
        return results

    async def test_ip(self, ip: str) -> Dict:
        """测试单个IP的各项性能"""
        self.logger.info(f"\n开始测试 IP: {ip}")
        
        results = {
            'ip': ip,
            'status': 'ok', 
            'tests': {},
            'http_test': None  # 新增HTTP测试结果
        }
        
        # 获取测试节点
        test_nodes = self.get_test_nodes(ip)
        self.logger.info(f"获取到测试节点: {test_nodes}")
        
        # 进行ping测试
        for isp, nodes in test_nodes.items():
            self.logger.info(f"\n测试 {isp} 线路:")
            for node_id in nodes:
                self.logger.info(f"Ping测试 IP {ip} 使用 {isp} 节点 {node_id}")
                try:
                    result = await self.test_single_ip(ip, node_id)
                    if result.get('available', False):
                        self.logger.info(f"IP {ip} - {isp} node {node_id} - "
                                    f"延迟: {result['latency']}ms, "
                                    f"丢包率: {result.get('loss', 0)}%")
                        if isp not in results['tests'] or \
                        results['tests'][isp].get('latency', float('inf')) > result.get('latency', float('inf')):
                            results['tests'][isp] = result
                            self.logger.info(f"更新 {isp} 最佳结果 - 延迟: {result['latency']}ms")
                    else:
                        self.logger.info(f"IP {ip} - {isp} node {node_id} - 测试不可用")
                except Exception as e:
                    self.logger.error(f"Error testing IP {ip} with {isp}: {str(e)}")
        
        self.logger.info(f"\nPing测试结果汇总: {results['tests']}")
        
        # 进行HTTP测试
        self.logger.info(f"\n开始HTTP测试 IP: {ip}")
        try:
            http_tester = HTTPTester(self.config)
            http_result = await http_tester.test_ip(ip)
            results['http_test'] = http_result
            self.logger.info(f"HTTP测试结果: {http_result}")
        except Exception as e:
            self.logger.error(f"HTTP测试失败 {ip}: {str(e)}")
            results['http_test'] = {'available': False, 'error': str(e)}
        
        self.logger.info(f"\n最终测试结果: {results}")
        return results

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
        try:
            headers = {
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'accept-language': 'zh-CN,zh;q=0.9',
                'content-type': 'application/x-www-form-urlencoded',
                'origin': 'https://www.itdog.cn',
                'referer': 'https://www.itdog.cn/batch_ping/',
                'user-agent': 'Mozilla/5.0'
            }

            try:
                response = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, 
                        lambda: self.session.get('https://www.itdog.cn/batch_ping/', 
                                            headers=headers, timeout=2)),
                    timeout=2
                )
                if response.status_code != 200:
                    return self._failed_result(node_id)
            except Exception:
                return self._failed_result(node_id)

            for retry in range(max_retries):
                try:
                    data = {
                        'host': ip,
                        'node_id': node_id,
                        'check_mode': 'ping'
                    }

                    response = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(None, 
                            lambda: self.session.post('https://www.itdog.cn/batch_ping/', 
                                                    headers=headers, data=data, timeout=2)),
                        timeout=2
                    )

                    if 'guard' in self.session.cookies:
                        guardret = self._set_ret(self.session.cookies['guard'])
                        self.session.cookies.set('guardret', guardret)

                    response = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(None, 
                            lambda: self.session.post('https://www.itdog.cn/batch_ping/', 
                                                    headers=headers, data=data, timeout=2)),
                        timeout=2
                    )
                    content = response.text

                    wss_match = re.search(r"""var wss_url='(.*)';""", content)
                    task_match = re.search(r"""var task_id='(.*)';""", content)

                    if not wss_match or not task_match:
                        raise ValueError("无法获取WebSocket信息")

                    wss_url = wss_match.group(1)
                    task_id = task_match.group(1)
                    task_token = hashlib.md5((task_id + "token_20230313000136kwyktxb0tgspm00yo5").encode()).hexdigest()[8:-8]

                    # 缩短WebSocket超时时间
                    async with websockets.connect(wss_url, open_timeout=2, ping_timeout=2) as ws:
                        await ws.send(json.dumps({
                            "task_id": task_id,
                            "task_token": task_token
                        }))

                        while True:
                            try:
                                msg = await asyncio.wait_for(ws.recv(), timeout=2)  # WebSocket接收超时改为2秒
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
                        await asyncio.sleep(0.5)  # 重试间隔改为0.5秒
                        continue
                    self.logger.error(f"测试 IP {ip} 失败: {str(e)}")

        except Exception as e:
            self.logger.error(f"测试 IP {ip} 时发生错误: {str(e)}")

        return self._failed_result(node_id)

    def _failed_result(self, node_id: str) -> Dict:
        """返回失败的测试结果"""
        return {
            'latency': float('inf'),
            'loss': 100,
            'available': False,
            'node_id': node_id
        }

    def get_test_nodes(self, ip: str) -> Dict[str, List[str]]:
        is_overseas = self.config.get('test_config', {}).get('overseas_mode', False)
        self.logger.info(f"Overseas mode: {is_overseas}")
        
        nodes = {}
        
        # 总是添加国内节点
        for isp in ['TELECOM', 'UNICOM', 'MOBILE']:
            nodes[isp] = [random.choice(self.NODE_IDS[isp])]
        
        # 如果开启了海外模式，添加一个海外节点
        if is_overseas:
            nodes['OVERSEAS'] = [random.choice(self.NODE_IDS['OVERSEAS'])]  # 只选择一个节点
        
        self.logger.info(f"Selected nodes: {nodes}")
        return nodes

    def save_intermediate_results(self, results: List[Dict]):
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            result_file = self.results_dir / f'test_results_intermediate_{timestamp}.json'
            
            with open(result_file, 'w') as f:
                json.dump(results, f, indent=2)
                
            self.logger.info(f"保存中间结果到 {result_file}")
            
        except Exception as e:
            self.logger.error(f"保存中间结果失败: {str(e)}")
