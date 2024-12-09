# Cloudflare 优选 IP

[![DNS Update](https://github.com/FutureUnreal/Cloudflare-Preference-IP/actions/workflows/dns-update.yml/badge.svg)](https://github.com/FutureUnreal/Cloudflare-Preference-IP/actions/workflows/dns-update.yml)

自动测试和优化 Cloudflare IP 的工具。使用多维度评估系统对 Cloudflare Anycast IP 进行网络质量测试，并自动更新 DNS 记录为最优 IP。

[English](./README_EN.md) | [简体中文](./README.md)

## ✨ 特性

- 🌐 多维度网络质量评估
  - Ping延迟、丢包率测试
  - HTTP性能(TTFB、总加载时间)分析
  - 多DNS服务商验证(阿里云、百度、谷歌)
  
- 📊 智能评分系统
  - 延迟权重: 60%
  - HTTP性能权重: 30% 
  - 稳定性权重: 10%
  
- 🔄 增量优化更新策略
  - 保持当前高分IP稳定性
  - 持续引入新的优质IP
  - 自动淘汰表现差的IP
  
- 🛡️ 多重验证机制
  - 多节点交叉验证
  - HTTP性能多DNS验证
  - 历史数据持续评估

## 🚀 快速开始

### GitHub Actions 配置

1. Fork 本仓库

2. 添加仓库密钥：
   - 进入仓库的 `Settings` > `Secrets and variables` > `Actions`
   - 根据你使用的 DNS 服务商添加对应的密钥：
```
# DNS服务商密钥
ALIYUN_KEY        # 阿里云 AccessKey ID
ALIYUN_SECRET     # 阿里云 AccessKey Secret
DNSPOD_ID         # DNSPod Secret ID
DNSPOD_KEY        # DNSPod Secret Key
HUAWEI_AK         # 华为云 Access Key
HUAWEI_SK         # 华为云 Secret Key

# 域名配置
DOMAIN            # 你的域名，例如：example.com
SUBDOMAIN         # 你的子域名，例如：cdn
```

3. 启用 GitHub Actions：
   - 进入仓库的 `Actions` 标签页
   - 启用 workflow
   - 测试会每5小时自动运行一次

### 本地部署

1. 克隆仓库：
```bash
git clone https://github.com/yourusername/Cloudflare-Preference-IP.git
cd Cloudflare-Preference-IP
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 修复 aliyunsdkcore：
```bash
# 进入 Python 包目录
cd .venv/lib/python3.12/site-packages/aliyunsdkcore

# 替换 six.py 文件到以下两个位置：
# - aliyunsdkcore/vendored/six.py
# - vendored/requests/packages/urllib3/packages/six.py
```

4. 更新配置文件
   - 配置 `config/settings.json`
   - 配置 `config/ip_ranges.json`

5. 运行测试：
```bash
python main.py
```

## ⚙️ 配置说明

### IP 范围配置 (config/ip_ranges.json)
```json
{
  "ip_ranges": [
    {
      "prefix": "104.16",    // IP前缀
      "start": 0,           // 起始范围
      "end": 255           // 结束范围
    }
  ],
  "skip_ips": [            // 跳过的IP列表
    "1.1.1.1",
    "1.0.0.1"
  ]
}
```

### 主配置文件 (config/settings.json)
```json
{
  "test_config": {
    "test_interval": 1,        // 测试间隔时间(秒)
    "sample_rate": 0.0002,     // 采样率
    "sample_size": 100,        // 采样数量
    "overseas_mode": true      // 是否测试境外线路
  },
  
  "evaluation": {
    "latency_thresholds": {
      "telecom_latency_threshold": 100,  // 电信延迟阈值(ms)  
      "unicom_latency_threshold": 100,   // 联通延迟阈值
      "mobile_latency_threshold": 100,   // 移动延迟阈值
      "overseas_latency_threshold": 150  // 海外延迟阈值
    },
    "http_ttfb_threshold": 200,         // HTTP首字节时间阈值(ms)
    "http_total_time_threshold": 1000    // HTTP总加载时间阈值(ms)
  },
  
  "dns": {
    "providers": {
      "aliyun": {
        "enabled": true,
        "access_key_id": "",    // 从环境变量 ALIYUN_KEY 获取
        "access_key_secret": "", // 从环境变量 ALIYUN_SECRET 获取
        "region": "cn-hangzhou"
      }
      // 其他DNS服务商配置类似
    },
    "max_records_per_line": {   // 每个线路保留的IP数量
      "TELECOM": 2,  // 电信2条记录
      "UNICOM": 2,   // 联通2条记录
      "MOBILE": 2,   // 移动2条记录
      "OVERSEAS": 1, // 境外1条记录
      "DEFAULT": 1   // 默认1条记录
    },
    "default_ttl": 600         // DNS记录TTL值
  },
  
  "domains": {
    "default": {
      "domain": "",              // 可选，默认从环境变量获取
      "subdomain": "",           // 可选，默认从环境变量获取
      "lines": ["CM", "CU", "CT", "AB"]  // 运营商线路配置
    }
  }
}
```

## 🔄 IP 优选策略

1. 初步筛选:
- Ping延迟低于阈值
- HTTP性能达标
- 稳定性符合要求

2. 多维度评分:
- 延迟得分(占比60%)
- HTTP性能得分(占比30%)
- 稳定性得分(占比10%)

3. 智能更新机制:
- 保留高分IP以维持稳定性
- 定期引入新的优质IP
- 历史表现作为重要参考
- 自动淘汰低质量IP

## 📊 测试结果

- test_results_latest.json:
  - 原始测试数据
  - 包含Ping和HTTP测试结果
  
- final_results_latest.json:
  - 最终分析结果 
  - 包含每个ISP最优IP
  - 详细的性能统计数据
  
- ip_history.json:
  - IP历史表现记录
  - 30天滚动数据

## 🌟 测试节点

使用 ITDOG 提供的以下运营商节点：

- 中国电信：覆盖全国主要省份节点
- 中国联通：覆盖全国范围测试节点
- 中国移动：覆盖主要城市节点
- 海外节点（可选）：香港、新加坡、日本等

## ⚠️ 免责声明

1. 本项目仅供学习和技术研究使用，不鼓励用于商业用途
2. 使用本项目导致的任何网络问题或主机问题，与本项目无关
3. 若使用本项目导致任何损失，由使用者自行承担后果
4. 本项目不保证测试结果的准确性和可用性
5. 本项目涉及的所有测速功能均通过模拟浏览器行为实现，请合理使用，避免对测速节点造成压力
6. 使用本项目时请遵守 ITDOG 网站的使用条款和规则
7. 请遵守当地法律法规，不得用于非法用途

如果当前 DNS 有移动、联通、电信线路的解析，执行后将会被覆盖。

## 致谢

本项目基于以下开源项目开发：

- [ddgth/cf2dns](https://github.com/ddgth/cf2dns) - 提供了 Cloudflare IP 优选和 DNS 自动切换的核心思路
- [wojiaoyishang/itdog-batch-ping](https://github.com/wojiaoyishang/itdog-batch-ping) - 提供了 ITDOG 节点测速的技术实现

感谢以上项目作者的开源贡献！

## 📃 许可证

[MIT 许可证](./LICENSE)

## 🤝 贡献

欢迎提交 Issues 和 Pull Requests！