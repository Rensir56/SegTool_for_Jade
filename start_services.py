#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
考古工具项目 - 本地服务管理脚本

支持启动、停止、重启和监控所有服务组件：
- RocketMQ (NameServer + Broker)
- Redis
- MySQL
- SAM服务器
- YOLO服务器
"""

import os
import sys
import time
import signal
import psutil
import subprocess
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional
import json

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('service_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ServiceManager:
    """本地服务管理器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.pid_file = self.project_root / 'service_pids.json'
        self.services = {
            'rocketmq_nameserver': {
                'name': 'RocketMQ NameServer',
                'cmd': self._get_rocketmq_nameserver_cmd(),
                'cwd': '/opt/rocketmq',
                'port': 9876,
                'health_check': self._check_rocketmq_nameserver
            },
            'rocketmq_broker': {
                'name': 'RocketMQ Broker',
                'cmd': self._get_rocketmq_broker_cmd(),
                'cwd': '/opt/rocketmq',
                'port': 10911,
                'health_check': self._check_rocketmq_broker,
                'depends_on': ['rocketmq_nameserver']
            },
            'redis': {
                'name': 'Redis Server',
                'cmd': ['redis-server'],
                'cwd': None,
                'port': 6379,
                'health_check': self._check_redis
            },
            'mysql': {
                'name': 'MySQL Server',
                'cmd': self._get_mysql_cmd(),
                'cwd': None,
                'port': 3306,
                'health_check': self._check_mysql,
                'system_service': True
            },
            'sam_server': {
                'name': 'SAM服务器',
                'cmd': ['python', 'main_rocketmq.py'],
                'cwd': str(self.project_root / 'server'),
                'port': 8080,
                'health_check': self._check_sam_server,
                'depends_on': ['rocketmq_broker', 'redis', 'mysql']
            },
            'yolo_server': {
                'name': 'YOLO服务器',
                'cmd': ['python', 'main_rocketmq.py'],
                'cwd': str(self.project_root / 'yolo-server'),
                'port': 8005,
                'health_check': self._check_yolo_server,
                'depends_on': ['rocketmq_broker', 'redis', 'mysql']
            }
        }
        
    def _get_rocketmq_nameserver_cmd(self) -> List[str]:
        """获取RocketMQ NameServer启动命令"""
        return ['nohup', 'bin/mqnamesrv']
        
    def _get_rocketmq_broker_cmd(self) -> List[str]:
        """获取RocketMQ Broker启动命令"""
        broker_conf = '/opt/rocketmq/conf/broker-local.conf'
        return ['nohup', 'bin/mqbroker', '-c', broker_conf]
        
    def _get_mysql_cmd(self) -> List[str]:
        """获取MySQL启动命令"""
        # 根据操作系统返回不同命令
        if sys.platform == 'darwin':  # macOS
            return ['brew', 'services', 'start', 'mysql']
        else:  # Linux
            return ['sudo', 'systemctl', 'start', 'mysql']
    
    def _load_pids(self) -> Dict:
        """加载服务PID信息"""
        if self.pid_file.exists():
            try:
                with open(self.pid_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_pids(self, pids: Dict):
        """保存服务PID信息"""
        with open(self.pid_file, 'w') as f:
            json.dump(pids, f, indent=2)
    
    def _check_port(self, port: int) -> bool:
        """检查端口是否被占用"""
        for conn in psutil.net_connections():
            if conn.laddr.port == port and conn.status == 'LISTEN':
                return True
        return False
    
    def _check_rocketmq_nameserver(self) -> bool:
        """检查RocketMQ NameServer状态"""
        try:
            result = subprocess.run(
                ['telnet', '127.0.0.1', '9876'],
                timeout=3,
                capture_output=True
            )
            return result.returncode == 0
        except:
            return self._check_port(9876)
    
    def _check_rocketmq_broker(self) -> bool:
        """检查RocketMQ Broker状态"""
        try:
            result = subprocess.run([
                '/opt/rocketmq/bin/mqadmin', 'clusterList', 
                '-n', '127.0.0.1:9876'
            ], timeout=5, capture_output=True)
            return result.returncode == 0
        except:
            return self._check_port(10911)
    
    def _check_redis(self) -> bool:
        """检查Redis状态"""
        try:
            result = subprocess.run(
                ['redis-cli', 'ping'],
                timeout=3,
                capture_output=True,
                text=True
            )
            return result.stdout.strip() == 'PONG'
        except:
            return self._check_port(6379)
    
    def _check_mysql(self) -> bool:
        """检查MySQL状态"""
        return self._check_port(3306)
    
    def _check_sam_server(self) -> bool:
        """检查SAM服务器状态"""
        try:
            import requests
            response = requests.get('http://localhost:8080/health', timeout=3)
            return response.status_code == 200
        except:
            return self._check_port(8080)
    
    def _check_yolo_server(self) -> bool:
        """检查YOLO服务器状态"""
        try:
            import requests
            response = requests.get('http://localhost:8005/health', timeout=3)
            return response.status_code == 200
        except:
            return self._check_port(8005)
    
    def start_service(self, service_name: str) -> bool:
        """启动单个服务"""
        service = self.services.get(service_name)
        if not service:
            logger.error(f"未知服务: {service_name}")
            return False
        
        # 检查依赖服务
        depends_on = service.get('depends_on', [])
        for dep in depends_on:
            if not self.is_service_running(dep):
                logger.info(f"启动依赖服务: {dep}")
                if not self.start_service(dep):
                    logger.error(f"依赖服务启动失败: {dep}")
                    return False
        
        # 检查服务是否已经运行
        if self.is_service_running(service_name):
            logger.info(f"{service['name']} 已经在运行")
            return True
        
        logger.info(f"启动 {service['name']}...")
        
        try:
            # 系统服务使用不同的启动方式
            if service.get('system_service'):
                result = subprocess.run(
                    service['cmd'],
                    cwd=service.get('cwd'),
                    check=True
                )
                # 等待系统服务启动
                time.sleep(3)
                
            else:
                # 普通进程
                if service_name.startswith('rocketmq'):
                    # RocketMQ需要特殊处理，使用nohup后台运行
                    cmd = service['cmd']
                    if service_name == 'rocketmq_nameserver':
                        log_file = '/opt/rocketmq/logs/namesrv.log'
                    else:
                        log_file = '/opt/rocketmq/logs/broker.log'
                    
                    cmd_str = ' '.join(cmd) + f' > {log_file} 2>&1 &'
                    process = subprocess.Popen(
                        cmd_str,
                        shell=True,
                        cwd=service.get('cwd')
                    )
                else:
                    # 其他服务
                    process = subprocess.Popen(
                        service['cmd'],
                        cwd=service.get('cwd'),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                
                # 保存PID
                if not service.get('system_service'):
                    pids = self._load_pids()
                    pids[service_name] = process.pid if hasattr(process, 'pid') else None
                    self._save_pids(pids)
            
            # 等待服务启动并验证
            max_retries = 30
            for i in range(max_retries):
                time.sleep(1)
                if service['health_check']():
                    logger.info(f"{service['name']} 启动成功")
                    return True
                
            logger.error(f"{service['name']} 启动失败或健康检查失败")
            return False
            
        except Exception as e:
            logger.error(f"启动 {service['name']} 时出错: {e}")
            return False
    
    def stop_service(self, service_name: str) -> bool:
        """停止单个服务"""
        service = self.services.get(service_name)
        if not service:
            logger.error(f"未知服务: {service_name}")
            return False
        
        if not self.is_service_running(service_name):
            logger.info(f"{service['name']} 未在运行")
            return True
        
        logger.info(f"停止 {service['name']}...")
        
        try:
            if service.get('system_service'):
                # 系统服务
                if sys.platform == 'darwin':  # macOS
                    cmd = ['brew', 'services', 'stop', 'mysql']
                else:  # Linux
                    cmd = ['sudo', 'systemctl', 'stop', 'mysql']
                subprocess.run(cmd, check=True)
                
            else:
                # 根据PID停止进程
                pids = self._load_pids()
                pid = pids.get(service_name)
                
                if pid:
                    try:
                        process = psutil.Process(pid)
                        process.terminate()
                        process.wait(timeout=10)
                    except psutil.NoSuchProcess:
                        pass
                    except psutil.TimeoutExpired:
                        process.kill()
                
                # 清理PID记录
                if service_name in pids:
                    del pids[service_name]
                    self._save_pids(pids)
            
            logger.info(f"{service['name']} 已停止")
            return True
            
        except Exception as e:
            logger.error(f"停止 {service['name']} 时出错: {e}")
            return False
    
    def is_service_running(self, service_name: str) -> bool:
        """检查服务是否在运行"""
        service = self.services.get(service_name)
        if not service:
            return False
        
        return service['health_check']()
    
    def start_all(self, service_list: Optional[List[str]] = None) -> bool:
        """启动所有服务或指定的服务列表"""
        services_to_start = service_list if service_list else list(self.services.keys())
        
        logger.info("开始启动服务...")
        
        # 按照依赖顺序启动
        start_order = [
            'mysql',
            'redis', 
            'rocketmq_nameserver',
            'rocketmq_broker',
            'sam_server',
            'yolo_server'
        ]
        
        for service_name in start_order:
            if service_name in services_to_start:
                if not self.start_service(service_name):
                    logger.error(f"服务启动失败: {service_name}")
                    return False
                time.sleep(2)  # 服务间启动间隔
        
        logger.info("所有服务启动完成!")
        return True
    
    def stop_all(self, service_list: Optional[List[str]] = None) -> bool:
        """停止所有服务或指定的服务列表"""
        services_to_stop = service_list if service_list else list(self.services.keys())
        
        logger.info("开始停止服务...")
        
        # 按照依赖顺序的逆序停止
        stop_order = [
            'yolo_server',
            'sam_server',
            'rocketmq_broker',
            'rocketmq_nameserver',
            'redis',
            'mysql'
        ]
        
        for service_name in stop_order:
            if service_name in services_to_stop:
                self.stop_service(service_name)
                time.sleep(1)  # 服务间停止间隔
        
        logger.info("所有服务已停止!")
        return True
    
    def restart_all(self, service_list: Optional[List[str]] = None) -> bool:
        """重启所有服务或指定的服务列表"""
        logger.info("重启服务...")
        if self.stop_all(service_list):
            time.sleep(5)  # 等待服务完全停止
            return self.start_all(service_list)
        return False
    
    def status(self) -> Dict[str, bool]:
        """获取所有服务状态"""
        status = {}
        for service_name, service in self.services.items():
            status[service_name] = {
                'name': service['name'],
                'running': self.is_service_running(service_name),
                'port': service['port']
            }
        return status
    
    def print_status(self):
        """打印服务状态"""
        status = self.status()
        
        print("\n" + "="*60)
        print("服务状态报告")
        print("="*60)
        
        for service_name, info in status.items():
            status_text = "🟢 运行中" if info['running'] else "🔴 已停止"
            print(f"{info['name']:20} | 端口:{info['port']:5} | {status_text}")
        
        print("="*60)
    
    def monitor(self, interval: int = 30):
        """监控服务状态"""
        logger.info(f"开始监控服务状态 (间隔: {interval}秒)")
        
        try:
            while True:
                self.print_status()
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("停止监控")


def main():
    parser = argparse.ArgumentParser(description='考古工具项目服务管理器')
    parser.add_argument('action', choices=['start', 'stop', 'restart', 'status', 'monitor'], 
                       help='操作类型')
    parser.add_argument('--services', type=str, help='指定服务列表，用逗号分隔')
    parser.add_argument('--monitor-interval', type=int, default=30, 
                       help='监控间隔时间（秒）')
    
    args = parser.parse_args()
    
    manager = ServiceManager()
    
    # 解析服务列表
    service_list = None
    if args.services:
        service_list = [s.strip() for s in args.services.split(',')]
        # 验证服务名称
        invalid_services = [s for s in service_list if s not in manager.services]
        if invalid_services:
            logger.error(f"无效的服务名称: {invalid_services}")
            logger.info(f"可用服务: {list(manager.services.keys())}")
            sys.exit(1)
    
    # 执行操作
    if args.action == 'start':
        success = manager.start_all(service_list)
        sys.exit(0 if success else 1)
        
    elif args.action == 'stop':
        success = manager.stop_all(service_list)
        sys.exit(0 if success else 1)
        
    elif args.action == 'restart':
        success = manager.restart_all(service_list)
        sys.exit(0 if success else 1)
        
    elif args.action == 'status':
        manager.print_status()
        
    elif args.action == 'monitor':
        manager.monitor(args.monitor_interval)


if __name__ == '__main__':
    main() 