#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地环境配置脚本
自动检查和配置考古工具项目的开发环境
"""

import os
import sys
import subprocess
import platform
import shutil
import urllib.request
import zipfile
import tarfile
from pathlib import Path
import json
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EnvironmentSetup:
    """环境配置管理器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.system = platform.system().lower()
        self.requirements = {
            'python': '3.8+',
            'java': '1.8+',
            'mysql': '8.0+',
            'redis': '6.0+',
            'node': '16+',
            'rocketmq': '5.1.4'
        }
        
    def check_command(self, command: str) -> bool:
        """检查命令是否可用"""
        return shutil.which(command) is not None
    
    def get_version(self, command: str, version_arg: str = '--version') -> str:
        """获取软件版本"""
        try:
            result = subprocess.run(
                [command, version_arg],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout.strip()
        except:
            return "未知"
    
    def check_python(self) -> bool:
        """检查Python环境"""
        logger.info("检查Python环境...")
        
        if not self.check_command('python3'):
            logger.error("Python3 未安装")
            return False
        
        version = self.get_version('python3')
        logger.info(f"Python版本: {version}")
        
        # 检查pip
        if not self.check_command('pip3'):
            logger.error("pip3 未安装")
            return False
        
        return True
    
    def check_java(self) -> bool:
        """检查Java环境"""
        logger.info("检查Java环境...")
        
        if not self.check_command('java'):
            logger.error("Java 未安装")
            self.print_java_install_guide()
            return False
        
        version = self.get_version('java', '-version')
        logger.info(f"Java版本: {version}")
        
        return True
    
    def check_mysql(self) -> bool:
        """检查MySQL"""
        logger.info("检查MySQL...")
        
        if not self.check_command('mysql'):
            logger.error("MySQL 未安装")
            self.print_mysql_install_guide()
            return False
        
        version = self.get_version('mysql')
        logger.info(f"MySQL版本: {version}")
        
        return True
    
    def check_redis(self) -> bool:
        """检查Redis"""
        logger.info("检查Redis...")
        
        if not self.check_command('redis-server'):
            logger.error("Redis 未安装")
            self.print_redis_install_guide()
            return False
        
        version = self.get_version('redis-server')
        logger.info(f"Redis版本: {version}")
        
        return True
    
    def check_node(self) -> bool:
        """检查Node.js"""
        logger.info("检查Node.js...")
        
        if not self.check_command('node'):
            logger.error("Node.js 未安装")
            self.print_node_install_guide()
            return False
        
        version = self.get_version('node')
        logger.info(f"Node.js版本: {version}")
        
        if not self.check_command('npm'):
            logger.error("npm 未安装")
            return False
        
        return True
    
    def check_rocketmq(self) -> bool:
        """检查RocketMQ"""
        logger.info("检查RocketMQ...")
        
        rocketmq_path = Path('/opt/rocketmq')
        if not rocketmq_path.exists():
            logger.warning("RocketMQ 未安装")
            return False
        
        logger.info(f"RocketMQ路径: {rocketmq_path}")
        return True
    
    def download_rocketmq(self) -> bool:
        """下载并安装RocketMQ"""
        logger.info("开始下载RocketMQ...")
        
        version = "5.1.4"
        filename = f"rocketmq-all-{version}-bin-release.zip"
        url = f"https://archive.apache.org/dist/rocketmq/{version}/{filename}"
        
        download_path = Path("/tmp") / filename
        install_path = Path("/opt/rocketmq")
        
        try:
            # 下载文件
            logger.info(f"下载 {url}")
            urllib.request.urlretrieve(url, download_path)
            
            # 解压
            logger.info("解压RocketMQ...")
            with zipfile.ZipFile(download_path, 'r') as zip_ref:
                zip_ref.extractall("/tmp")
            
            # 移动到安装目录
            extracted_path = Path("/tmp") / f"rocketmq-all-{version}-bin-release"
            if install_path.exists():
                shutil.rmtree(install_path)
            
            shutil.move(str(extracted_path), str(install_path))
            
            # 设置权限
            os.chmod(install_path / "bin" / "mqnamesrv", 0o755)
            os.chmod(install_path / "bin" / "mqbroker", 0o755)
            os.chmod(install_path / "bin" / "mqadmin", 0o755)
            
            # 清理
            download_path.unlink()
            
            logger.info("RocketMQ安装完成")
            return True
            
        except Exception as e:
            logger.error(f"RocketMQ安装失败: {e}")
            return False
    
    def create_rocketmq_config(self):
        """创建RocketMQ配置文件"""
        config_path = Path("/opt/rocketmq/conf/broker-local.conf")
        
        config_content = """brokerClusterName = DefaultCluster
brokerName = broker-a
brokerId = 0
deleteWhen = 04
fileReservedTime = 120
brokerRole = ASYNC_MASTER
flushDiskType = ASYNC_FLUSH
brokerIP1 = 127.0.0.1
listenPort = 10911
namesrvAddr = 127.0.0.1:9876
storePathRootDir = /opt/rocketmq/store
storePathCommitLog = /opt/rocketmq/store/commitlog
maxMessageSize = 67108864
"""
        
        try:
            with open(config_path, 'w') as f:
                f.write(config_content)
            logger.info(f"RocketMQ配置文件创建: {config_path}")
        except Exception as e:
            logger.error(f"配置文件创建失败: {e}")
    
    def setup_python_env(self) -> bool:
        """配置Python环境"""
        logger.info("配置Python环境...")
        
        # 创建虚拟环境
        venv_paths = [
            self.project_root / "server" / "venv",
            self.project_root / "yolo-server" / "venv"
        ]
        
        for venv_path in venv_paths:
            if not venv_path.exists():
                try:
                    subprocess.run(
                        ['python3', '-m', 'venv', str(venv_path)],
                        check=True
                    )
                    logger.info(f"虚拟环境创建: {venv_path}")
                except subprocess.CalledProcessError as e:
                    logger.error(f"虚拟环境创建失败: {e}")
                    return False
        
        return True
    
    def install_python_dependencies(self) -> bool:
        """安装Python依赖"""
        logger.info("安装Python依赖...")
        
        dependencies = [
            (self.project_root / "server", "requirements.txt"),
            (self.project_root / "server", "requirements_rocketmq.txt"),
            (self.project_root / "yolo-server", "requirements.txt")
        ]
        
        for directory, req_file in dependencies:
            req_path = directory / req_file
            if req_path.exists():
                venv_path = directory / "venv"
                pip_cmd = venv_path / "bin" / "pip"
                
                if self.system == "windows":
                    pip_cmd = venv_path / "Scripts" / "pip.exe"
                
                try:
                    subprocess.run(
                        [str(pip_cmd), 'install', '-r', str(req_path)],
                        check=True
                    )
                    logger.info(f"依赖安装完成: {req_path}")
                except subprocess.CalledProcessError as e:
                    logger.error(f"依赖安装失败: {e}")
                    return False
        
        return True
    
    def setup_frontend_env(self) -> bool:
        """配置前端环境"""
        logger.info("配置前端环境...")
        
        frontend_path = self.project_root / "front"
        if not frontend_path.exists():
            logger.error("前端目录不存在")
            return False
        
        try:
            # 安装npm依赖
            subprocess.run(
                ['npm', 'install'],
                cwd=frontend_path,
                check=True
            )
            logger.info("前端依赖安装完成")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"前端依赖安装失败: {e}")
            return False
    
    def create_env_files(self):
        """创建环境配置文件"""
        logger.info("创建环境配置文件...")
        
        # 服务器环境变量
        server_env = {
            'DATABASE_HOST': 'localhost',
            'DATABASE_PORT': '3306',
            'DATABASE_NAME': 'archaeological_tool',
            'DATABASE_USER': 'arch_user',
            'DATABASE_PASSWORD': 'arch_password_2024',
            'REDIS_HOST': 'localhost',
            'REDIS_PORT': '6379',
            'ROCKETMQ_NAMESERVER': '127.0.0.1:9876',
            'SAM_MODEL_PATH': './models/sam_vit_h_4b8939.pth',
            'YOLO_MODEL_PATH': './models/yolov8n.pt'
        }
        
        env_files = [
            self.project_root / "server" / ".env",
            self.project_root / "yolo-server" / ".env"
        ]
        
        for env_file in env_files:
            try:
                with open(env_file, 'w') as f:
                    for key, value in server_env.items():
                        f.write(f"{key}={value}\n")
                logger.info(f"环境文件创建: {env_file}")
            except Exception as e:
                logger.error(f"环境文件创建失败: {e}")
    
    def print_java_install_guide(self):
        """打印Java安装指南"""
        guides = {
            'linux': "sudo apt install openjdk-8-jdk  # Ubuntu/Debian\nsudo yum install java-1.8.0-openjdk  # CentOS/RHEL",
            'darwin': "brew install openjdk@8",
            'windows': "下载并安装Oracle JDK或OpenJDK"
        }
        print(f"\nJava安装指南:\n{guides.get(self.system, guides['windows'])}")
    
    def print_mysql_install_guide(self):
        """打印MySQL安装指南"""
        guides = {
            'linux': "sudo apt install mysql-server  # Ubuntu/Debian\nsudo yum install mysql-server  # CentOS/RHEL",
            'darwin': "brew install mysql",
            'windows': "下载并安装MySQL Community Server"
        }
        print(f"\nMySQL安装指南:\n{guides.get(self.system, guides['windows'])}")
    
    def print_redis_install_guide(self):
        """打印Redis安装指南"""
        guides = {
            'linux': "sudo apt install redis-server  # Ubuntu/Debian\nsudo yum install redis  # CentOS/RHEL",
            'darwin': "brew install redis",
            'windows': "下载并安装Redis for Windows"
        }
        print(f"\nRedis安装指南:\n{guides.get(self.system, guides['windows'])}")
    
    def print_node_install_guide(self):
        """打印Node.js安装指南"""
        guides = {
            'linux': "curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -\nsudo apt-get install -y nodejs",
            'darwin': "brew install node",
            'windows': "下载并安装Node.js"
        }
        print(f"\nNode.js安装指南:\n{guides.get(self.system, guides['windows'])}")
    
    def check_all_requirements(self) -> bool:
        """检查所有环境要求"""
        logger.info("开始环境检查...")
        
        checks = [
            ('Python', self.check_python),
            ('Java', self.check_java),
            ('MySQL', self.check_mysql),
            ('Redis', self.check_redis),
            ('Node.js', self.check_node),
            ('RocketMQ', self.check_rocketmq)
        ]
        
        missing = []
        for name, check_func in checks:
            if not check_func():
                missing.append(name)
        
        if missing:
            logger.error(f"缺少组件: {', '.join(missing)}")
            return False
        
        logger.info("所有环境检查通过!")
        return True
    
    def setup_complete_environment(self) -> bool:
        """完整环境配置"""
        logger.info("开始完整环境配置...")
        
        # 检查基础组件
        if not self.check_python():
            return False
        
        if not self.check_java():
            return False
        
        # 安装RocketMQ（如果需要）
        if not self.check_rocketmq():
            if not self.download_rocketmq():
                return False
            self.create_rocketmq_config()
        
        # 配置Python环境
        if not self.setup_python_env():
            return False
        
        if not self.install_python_dependencies():
            return False
        
        # 配置前端环境
        if not self.setup_frontend_env():
            return False
        
        # 创建配置文件
        self.create_env_files()
        
        logger.info("环境配置完成!")
        return True
    
    def generate_setup_report(self):
        """生成配置报告"""
        report = {
            'timestamp': str(datetime.now()),
            'system': platform.system(),
            'python_version': self.get_version('python3'),
            'java_version': self.get_version('java', '-version'),
            'mysql_available': self.check_command('mysql'),
            'redis_available': self.check_command('redis-server'),
            'node_version': self.get_version('node'),
            'rocketmq_installed': Path('/opt/rocketmq').exists()
        }
        
        report_file = self.project_root / 'environment_report.json'
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        logger.info(f"环境报告生成: {report_file}")


def main():
    """主函数"""
    setup = EnvironmentSetup()
    
    print("="*60)
    print("考古工具项目 - 环境配置脚本")
    print("="*60)
    
    import argparse
    parser = argparse.ArgumentParser(description='环境配置脚本')
    parser.add_argument('--check-only', action='store_true', 
                       help='仅检查环境，不进行配置')
    parser.add_argument('--install-rocketmq', action='store_true',
                       help='强制安装RocketMQ')
    
    args = parser.parse_args()
    
    if args.install_rocketmq:
        setup.download_rocketmq()
        setup.create_rocketmq_config()
        return
    
    if args.check_only:
        success = setup.check_all_requirements()
        setup.generate_setup_report()
    else:
        success = setup.setup_complete_environment()
        setup.generate_setup_report()
    
    if success:
        print("\n" + "="*60)
        print("环境配置成功!")
        print("接下来运行:")
        print("1. python server/database_migration.py  # 初始化数据库")
        print("2. python start_services.py start       # 启动所有服务")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("环境配置失败，请检查错误信息")
        print("="*60)
        sys.exit(1)


if __name__ == '__main__':
    from datetime import datetime
    main() 