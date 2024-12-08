import re
import json
import base64
import hashlib
import asyncio
import logging
import requests
import websockets
import random
from typing import Dict, List
from urllib.parse import urlparse

class HTTPTester:
    def __init__(self, config: Dict):
        self.config = config
        self.logger = logging.getLogger('HTTPTester')
        self.session = requests.Session()
        
        # DNS服务器配置
        self.dns_servers = {
            'ALIYUN': '223.5.5.5',    # 阿里DNS
            'BAIDU': '180.76.76.76',   # 百度DNS
            'GOOGLE': '8.8.8.8'        # 谷歌DNS
        }
        
        # 超时设置
        self.timeout = config.get('http_test', {}).get('timeout', 5)
        
        self.headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'zh-CN;q=0.9,en-GB;q=0.7,en-US;q=0.6',
            'Cache-Control': 'max-age=0',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://www.itdog.cn',
            'Referer': 'https://www.itdog.cn/http/',
            'Sec-Ch-Ua': '"Microsoft Edge";v="131", "Chromium";v="131", "Not A Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edge/131.0.0.0'
        }

    def _x(self, input_str: str, key: str) -> str:
        """加密函数"""
        output = ""
        key = key + "PTNo2n3Ev5"
        for i, char in enumerate(input_str):
            char_code = ord(char) ^ ord(key[i % len(key)])
            output += chr(char_code)
        return output

    def _set_ret(self, guard_cookie: str) -> str:
        """设置guardret cookie"""
        prefix = guard_cookie[:8]
        num = int(guard_cookie[12:]) if len(guard_cookie) > 12 else 0
        val = num * 2 + 18 - 2
        encrypted = self._x(str(val), prefix)
        return base64.b64encode(encrypted.encode()).decode()

    async def _get_websocket_data(self, wss_url: str, task_id: str, task_token: str) -> Dict:
        result = {
            'available': False,
            'ttfb': float('inf'),
            'total_time': float('inf'),
            'error': None
        }
        
        try:
            async with websockets.connect(wss_url) as websocket:
                await websocket.send(json.dumps({
                    "task_id": task_id,
                    "task_token": task_token
                }))
                
                best_result = None  # 记录最好的测试结果
                
                while True:
                    try:
                        msg = await asyncio.wait_for(websocket.recv(), timeout=5)
                        
                        data = json.loads(msg)
                        
                        if data.get('type') == 'finished':
                            break
                            
                        if data.get('type') == 'success':
                            http_code = int(data.get('http_code', 0))
                            # 如果是有效的响应
                            if http_code > 0:  # 修改判断条件
                                current_time = float(data.get('all_time', float('inf')))
                                # 更新最佳结果
                                if best_result is None or current_time < best_result['all_time']:
                                    best_result = {
                                        'all_time': current_time,
                                        'ttfb': float(data.get('connect_time', float('inf'))),  # 使用连接时间作为TTFB
                                        'total_time': current_time,
                                        'http_code': http_code,
                                        'head': data.get('head', '')
                                    }
                    
                    except asyncio.TimeoutError:
                        break
                    except Exception as e:
                        self.logger.error(f"处理WebSocket消息失败: {str(e)}")
                
                # 使用最佳结果更新返回值
                if best_result and best_result['all_time'] < float('inf'):
                    result['available'] = True
                    result['ttfb'] = best_result['ttfb']
                    result['total_time'] = best_result['total_time']
                    self.logger.info(f"使用最佳测试结果: TTFB={result['ttfb']}, TotalTime={result['total_time']}")
                    
        except Exception as e:
            result['error'] = str(e)
            self.logger.error(f"WebSocket连接失败: {str(e)}")
        
        return result

    async def test_single_ip_with_dns(self, ip: str, dns_type: str, dns_server: str) -> Dict:
        """使用指定DNS服务器测试单个IP的HTTP性能"""
        try:
            # 更新测试参数
            data = {
                'line': '',
                'host': ip,
                'host_s': ip,
                'check_mode': 'fast',
                'ipv4': '',
                'method': 'get',
                'referer': '',
                'ua': '',
                'cookies': '',
                'redirect_num': '5',
                'dns_server_type': 'custom',
                'dns_server': dns_server
            }

            # 首次请求获取guard cookie
            if 'guardret' not in self.session.cookies:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.session.post('https://www.itdog.cn/http/',
                                           headers=self.headers,
                                           data=data,
                                           timeout=self.timeout)
                )

            if 'guard' in self.session.cookies:
                guardret = self._set_ret(self.session.cookies['guard'])
                self.session.cookies.set('guardret', guardret)
                self.logger.info(f"Cookie设置成功: guard={self.session.cookies.get('guard')}, guardret={guardret}")

            # 发送测试请求
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.session.post('https://www.itdog.cn/http/',
                                       headers=self.headers,
                                       data=data,
                                       timeout=self.timeout)
            )

            # 解析WebSocket信息
            content = response.text
            wss_match = re.search(r"""var wss_url='(.*)';""", content)
            task_match = re.search(r"""var task_id='(.*)';""", content)

            if not wss_match or not task_match:
                self.logger.error("未找到WebSocket信息")
                return {'available': False, 'error': 'WebSocket信息获取失败'}

            wss_url = wss_match.group(1)
            task_id = task_match.group(1)
            task_token = hashlib.md5(
                (task_id + "token_20230313000136kwyktxb0tgspm00yo5").encode()
            ).hexdigest()[8:-8]

            # 获取测试结果
            result = await self._get_websocket_data(wss_url, task_id, task_token)
            
            return result

        except Exception as e:
            self.logger.error(f"测试失败: {str(e)}")
            return {
                'available': False,
                'error': str(e),
                'ttfb': float('inf'),
                'total_time': float('inf')
            }

    async def test_ip(self, ip: str) -> Dict:
        """测试IP在所有DNS服务器上的性能"""
        results = {}
        
        # 对每个DNS服务器进行测试
        for dns_type, dns_server in self.dns_servers.items():
            result = await self.test_single_ip_with_dns(ip, dns_type, dns_server)
            results[dns_type] = result
            
        # 汇总结果
        available_results = {
            dns_type: result 
            for dns_type, result in results.items() 
            if result.get('available', False)
        }
        
        if not available_results:
            return {
                'available': False,
                'ttfb': float('inf'),
                'total_time': float('inf'),
                'results': results
            }
            
        # 计算平均性能指标
        avg_ttfb = sum(r['ttfb'] for r in available_results.values()) / len(available_results)
        avg_total_time = sum(r['total_time'] for r in available_results.values()) / len(available_results)
            
        return {
            'available': True,
            'ttfb': avg_ttfb,
            'total_time': avg_total_time,
            'results': results,
            # 分别保存不同DNS的测试结果，用于后续评估
            'aliyun_result': results.get('ALIYUN', {}),
            'baidu_result': results.get('BAIDU', {}),
            'google_result': results.get('GOOGLE', {})
        }

    async def start(self, ip_list: List[str]) -> List[Dict]:
        """开始测试一批IP"""
        results = []
        for ip in ip_list:
            try:
                self.logger.info(f"测试 IP: {ip}")
                result = await self.test_ip(ip)
                result['ip'] = ip
                result['status'] = 'ok'
                results.append(result)
            except Exception as e:
                self.logger.error(f"测试 IP {ip} 失败: {str(e)}")
                results.append({
                    'ip': ip,
                    'status': 'error',
                    'error': str(e)
                })
        return results