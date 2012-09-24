#encoding=utf-8

'''
通用常量定义
'''
#程序版本号,当gossAgent和gossMaster的RPC方法有变更时，请提升该版本号                                                                |~
APP_VERSION = 2

#程序需要更新                                                                                                                       |~
NEED_UPDATE = 8888

#连接被拒绝
CONNECTION_REFUSED = -9999

#服务器状态：0-停止 1-运行 2-维护
STATUS_STOP = 0
STATUS_RUN = 1
STATUS_VINDICATE = 2

#服务器类型 0-网关服 1-登录服 2-游戏服
SERVER_GATE = 0
SERVER_LOGIN = 1
SERVER_GAME = 2

#登录服同步配置 0-正常配置 2-同步配置
SYNC_NORMAL = 0
SYNC_SYNC = 2

#agent还未注册
AGENT_NOT_REGISTER = -2

#服务器不存在
SERVER_NOT_EXIST = -1

#操作成功
SUCCESS = 0

#操作失败
FAIL = 1

#非法操作
ILEGAL_OPERATE = 2
