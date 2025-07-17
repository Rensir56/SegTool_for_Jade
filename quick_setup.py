#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
考古工具项目 - 一键部署脚本
自动完成环境配置、数据库初始化和服务启动
"""

import os
import sys
import time
import subprocess
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class QuickSetup:
    """一键部署管理器"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        
    def print_banner(self):
        """打印欢迎信息"""
        print("=" * 80)
        print("🏺 考古工具项目 - 一键部署脚本")
        print("=" * 80)
        print("📋 本脚本将自动完成:")
        print("   1. 环境检查和配置")
        print("   2. RocketMQ安装和配置")
        print("   3. 数据库初始化")
        print("   4. Python依赖安装")
        print("   5. 服务启动验证")
        print("=" * 80)
        print()
    
    def check_python_requirements(self) -> bool:
        """检查Python依赖"""
        logger.info("检查Python依赖包...")
        
        required_packages = [
            'mysql-connector-python',
            'redis',
            'psutil',
            'requests'
        ]
        
        missing_packages = []
        for package in required_packages:
            try:
                __import__(package.replace('-', '_'))
                logger.info(f"✅ {package}")
            except ImportError:
                missing_packages.append(package)
                logger.warning(f"❌ {package}")
        
        if missing_packages:
            logger.info("安装缺失的Python包...")
            try:
                subprocess.run([
                    sys.executable, '-m', 'pip', 'install'
                ] + missing_packages, check=True)
                logger.info("Python包安装完成")
                return True
            except subprocess.CalledProcessError as e:
                logger.error(f"Python包安装失败: {e}")
                return False
        
        return True
    
    def run_environment_setup(self) -> bool:
        """运行环境配置"""
        logger.info("开始环境配置...")
        
        try:
            result = subprocess.run([
                sys.executable, 'setup_local_environment.py'
            ], cwd=self.project_root, check=True)
            logger.info("环境配置完成")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"环境配置失败: {e}")
            return False
    
    def run_database_migration(self) -> bool:
        """运行数据库迁移"""
        logger.info("开始数据库初始化...")
        
        try:
            result = subprocess.run([
                sys.executable, 'database_migration.py'
            ], cwd=self.project_root / 'server', check=True)
            logger.info("数据库初始化完成")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"数据库初始化失败: {e}")
            logger.info("提示: 请确保MySQL服务已启动，并且已创建数据库和用户")
            return False
    
    def start_services(self) -> bool:
        """启动所有服务"""
        logger.info("启动服务...")
        
        try:
            result = subprocess.run([
                sys.executable, 'start_services.py', 'start'
            ], cwd=self.project_root, check=True)
            logger.info("服务启动完成")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"服务启动失败: {e}")
            return False
    
    def verify_deployment(self) -> bool:
        """验证部署结果"""
        logger.info("验证部署结果...")
        
        # 等待服务启动
        time.sleep(10)
        
        try:
            result = subprocess.run([
                sys.executable, 'start_services.py', 'status'
            ], cwd=self.project_root, check=True)
            
            logger.info("部署验证完成")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"部署验证失败: {e}")
            return False
    
    def print_success_info(self):
        """打印成功信息"""
        print("\n" + "=" * 80)
        print("🎉 部署成功！")
        print("=" * 80)
        print("📊 服务访问地址:")
        print("   SAM服务器:    http://localhost:8080")
        print("   YOLO服务器:   http://localhost:8005")
        print("   前端界面:     http://localhost:8000 (需要启动前端服务)")
        print()
        print("👤 默认管理员账户:")
        print("   用户名: admin")
        print("   密码:   admin123")
        print()
        print("🛠️  常用命令:")
        print("   查看服务状态: python start_services.py status")
        print("   重启服务:     python start_services.py restart")
        print("   停止服务:     python start_services.py stop")
        print("   监控服务:     python start_services.py monitor")
        print()
        print("📁 日志文件位置:")
        print("   服务管理:     service_manager.log")
        print("   RocketMQ:     /opt/rocketmq/logs/")
        print("   SAM服务器:    server/logs/")
        print("   YOLO服务器:   yolo-server/logs/")
        print("=" * 80)
    
    def print_failure_info(self):
        """打印失败信息"""
        print("\n" + "=" * 80)
        print("❌ 部署失败")
        print("=" * 80)
        print("🔧 故障排除步骤:")
        print("1. 检查日志文件: service_manager.log")
        print("2. 验证环境配置: python setup_local_environment.py --check-only")
        print("3. 手动创建数据库:")
        print("   mysql -u root -p")
        print("   CREATE DATABASE archaeological_tool;")
        print("   CREATE USER 'arch_user'@'localhost' IDENTIFIED BY 'arch_password_2024';")
        print("   GRANT ALL PRIVILEGES ON archaeological_tool.* TO 'arch_user'@'localhost';")
        print("4. 重新运行: python quick_setup.py")
        print()
        print("📞 技术支持:")
        print("   请将 service_manager.log 和错误信息发送给技术支持团队")
        print("=" * 80)
    
    def run_quick_setup(self) -> bool:
        """运行完整的快速部署"""
        self.print_banner()
        
        # 询问用户确认
        response = input("是否开始自动部署? (y/N): ").strip().lower()
        if response != 'y' and response != 'yes':
            print("部署已取消")
            return False
        
        print("\n🚀 开始部署...")
        
        steps = [
            ("检查Python依赖", self.check_python_requirements),
            ("环境配置", self.run_environment_setup),
            ("数据库初始化", self.run_database_migration),
            ("启动服务", self.start_services),
            ("验证部署", self.verify_deployment)
        ]
        
        for step_name, step_func in steps:
            logger.info(f"执行步骤: {step_name}")
            
            if not step_func():
                logger.error(f"步骤失败: {step_name}")
                self.print_failure_info()
                return False
            
            logger.info(f"步骤完成: {step_name}")
            time.sleep(2)  # 步骤间暂停
        
        self.print_success_info()
        return True


def main():
    """主函数"""
    setup = QuickSetup()
    
    try:
        success = setup.run_quick_setup()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n部署被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"部署过程中发生未知错误: {e}")
        setup.print_failure_info()
        sys.exit(1)


if __name__ == '__main__':
    main() 