import json
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.dnspod.v20210323 import dnspod_client, models

class DNSPod:
    def __init__(self, secret_id: str, secret_key: str):
        self.SecretId = secret_id  
        self.secretKey = secret_key
        self.cred = credential.Credential(secret_id, secret_key)
        self.client = dnspod_client.DnspodClient(self.cred, "")

    def del_record(self, domain: str, record_id: int) -> dict:
        """删除解析记录"""
        try:
            client = dnspod_client.DnspodClient(self.cred, "")
            req_model = models.DeleteRecordRequest()
            params = {
                "Domain": domain,
                "RecordId": record_id
            }
            req_model.from_json_string(json.dumps(params))
            resp = client.DeleteRecord(req_model)
            resp = json.loads(resp.to_json_string())
            resp["code"] = 0
            resp["message"] = "None"
            return resp
            
        except TencentCloudSDKException as e:
            return {
                "code": e.code,
                "message": e.message
            }

    def get_record(self, domain: str, length: int, sub_domain: str, record_type: str) -> dict:
        """获取解析记录"""
        try:
            client = dnspod_client.DnspodClient(self.cred, "")
            req_model = models.DescribeRecordListRequest()
            params = {
                "Domain": domain,
                "Subdomain": sub_domain,
                "RecordType": record_type,
                "Limit": length
            }
            req_model.from_json_string(json.dumps(params))

            resp = client.DescribeRecordList(req_model)
            resp = json.loads(resp.to_json_string())
            
            # 格式化返回数据
            temp_resp = {
                "code": 0,
                "data": {
                    "records": [],
                    "domain": {
                        "grade": self.get_domain(domain)["DomainInfo"]["Grade"]
                    }
                }
            }
            
            # 格式化记录
            for record in resp['RecordList']:
                temp_resp["data"]["records"].append(self._format_record(record))
                
            return temp_resp
            
        except TencentCloudSDKException:
            return {
                "code": 0,
                "data": {
                    "records": [],
                    "domain": {
                        "grade": self.get_domain(domain)["DomainInfo"]["Grade"]
                    }
                }
            }

    def create_record(self, domain: str, sub_domain: str, value: str, 
                     record_type: str = "A", line: str = "默认", ttl: int = 600) -> dict:
        """创建解析记录"""
        try:
            client = dnspod_client.DnspodClient(self.cred, "")
            req = models.CreateRecordRequest()
            params = {
                "Domain": domain,
                "SubDomain": sub_domain,
                "RecordType": record_type,
                "RecordLine": line,
                "Value": value,
                "TTL": ttl
            }
            req.from_json_string(json.dumps(params))

            resp = client.CreateRecord(req)
            resp = json.loads(resp.to_json_string())
            resp["code"] = 0
            resp["message"] = "None"
            return resp
            
        except TencentCloudSDKException as e:
            return {
                "code": e.code,
                "message": e.message
            }

    def update_record(self, domain: str, record_id: int, sub_domain: str, 
                     value: str, record_type: str = "A", line: str = "默认", ttl: int = 600) -> dict:
        """更新解析记录"""
        try:
            client = dnspod_client.DnspodClient(self.cred, "")
            req = models.ModifyRecordRequest()
            params = {
                "Domain": domain,
                "RecordId": record_id,
                "SubDomain": sub_domain,
                "RecordType": record_type,
                "RecordLine": line,
                "Value": value,
                "TTL": ttl
            }
            req.from_json_string(json.dumps(params))

            resp = client.ModifyRecord(req)
            resp = json.loads(resp.to_json_string())
            resp["code"] = 0
            resp["message"] = "None"
            return resp
            
        except TencentCloudSDKException as e:
            return {
                "code": e.code,
                "message": e.message
            }

    def get_domain(self, domain: str) -> dict:
        """获取域名信息"""
        client = dnspod_client.DnspodClient(self.cred, "")
        req = models.DescribeDomainRequest()
        params = {"Domain": domain}
        req.from_json_string(json.dumps(params))
        resp = client.DescribeDomain(req)
        return json.loads(resp.to_json_string())

    def _format_record(self, record: dict) -> dict:
        """格式化记录"""
        new_record = {}
        record["id"] = record['RecordId']
        for key in record:
            new_record[key.lower()] = record[key]
        return new_record