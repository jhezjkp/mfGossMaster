#!/usr/bin/env python
#encoding=utf-8

import sys
import os
import re
import subprocess
import threading
import time
import shutil
import datetime
import logging
import hashlib
import xml.dom.minidom
import zipfile

from flask import Flask, render_template, send_from_directory, request, redirect, url_for, session, jsonify
from flaskext.principal import Principal, Permission, ActionNeed, TypeNeed, Identity, identity_changed, PermissionDenied
from flaskext.babel import Babel, gettext as _
import zerorpc

from gossMaster import Master
from constants import *


#web监听端口
httpPort = 9999
#分类
categoryMap = {}
#用户
userMap = {}
#用户角色对应关系
userRoleMap = {}
#角色权限对应关系
rolePermissionMap = {}
#web应用
app = Flask(__name__)
#配置secret才能使用session
app.config.update(
    SECRET_KEY='morefun_sg_manage'
)
#装载认证扩展
principals = Principal(app)
##########权限配置##########
update_script_permission = Permission(ActionNeed('update_script'))
update_app_permission = Permission(ActionNeed('update_app'))
vindicate_game_permission = Permission(ActionNeed('vindicate_game'))
view_console_permission = Permission(ActionNeed('view_console'))
switch_sync_config_permission = Permission(ActionNeed('switch_sync_config'))
backup_database_permission = Permission(ActionNeed('backup_database'))
#游戏服启停操作
manage_game_app_permission = Permission(ActionNeed('manage_game_app'))
#其他应用启停操作
manage_app_permission = Permission(ActionNeed('manage_app'))
#已登录权限,所有已登录用户都应该授予该权限
auth_permission = Permission(TypeNeed('auth'))
#国际化
babel = Babel(app)
#master
master = None


@babel.localeselector
def get_locale():
    #语言匹配
    return request.accept_languages.best_match(['zh_CN', 'zh_TW', 'en_US'])


#订阅identity_loaded信号，当接收到该信号时，被修饰的方法将被执行
@identity_changed.connect
def on_identity_loaded(sender, identity):
    #该方法将用户与角色等关联起来
    #即将登录的用户与授权信息绑定
    for role, users in userRoleMap.items():
        if identity.name in users:
            for action in rolePermissionMap.get(role):
                identity.provides.add(ActionNeed(action))
    #授予用户以登录权限
    identity.provides.add(TypeNeed('auth'))


@principals.identity_loader
def load_identity_from_session():
    #每收到一次request请求便从会话中获取身份信息(如果有的话)
    if 'identity.name' in session and 'identity.auth_type' in session:
        return session.get('identity')


@principals.identity_saver
def save_identity_to_weird_usecase(identity):
    #request请求结束后或identity有变更时将身份信息保存到会话中
    session['identity'] = identity
    session['identity.name'] = identity.name
    session['identity.auth_type'] = identity.auth_type
    session.modified = True
    #应用服务器分类放到会话中
    session['categoryMap'] = categoryMap


@app.errorhandler(403)
@app.errorhandler(PermissionDenied)
def page_not_found(e):
    if session.get('identity.name'):  # 已登录过的
        return redirect(url_for('denied'))
    #未登录的先保存请求的目标页面
    session['redirected_from'] = request.url
    #再转向到登录页
    return redirect(url_for('login'))


# handle login failed
#@app.errorhandler(401)
#def page_not_found(e):
#    return Response('Login failed')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in userMap and password == userMap.get(username):
            identity = Identity(username)
            identity_changed.send(app, identity=identity)
            #设置默认显示所有分类
            session['category'] = 0
            if session.get('redirected_from'):
                return redirect(session['redirected_from'])
            else:
                return redirect(url_for('index'))
        else:
            #return abort(401)
            return render_template('login.html', errorMsg='用户名或密码错误')
    else:
        return render_template('login.html')


@app.route('/logout')
def logout():
    for key in ['identity', 'identity.name', 'identity.auth_type', 'redirected_from']:
        try:
            del session[key]
        except:
            pass
    return redirect(url_for('index'))


@app.route('/denied')
def denied():
    return render_template('denied.html')


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/')
@auth_permission.require()
def index(successMsg=None, errorMsg=None):
    #首页(检查各服状态)
    servers = {}
    category = session.get('category', 0)
    for server in master.appMap.values():
        if category == 0:
            servers[server.id] = server
        elif category == server.category:
            servers[server.id] = server
    errorMsg = request.args.get('errorMsg', None)
    successMsg = request.args.get('successMsg', None)
    return render_template('index.html', appServerMap=servers, successMsg=successMsg, errorMsg=errorMsg)


@app.route('/showAppServersByCategory/<int:category>')
def showAppServersByCategory(category):
    #显示指定分类的应用服
    session['category'] = category
    return redirect(url_for('index'))


#@app.route('/shutdown')
#def shutdown():
    #'''停止应用'''
    #func = request.environ.get('werkzeug.server.shutdown')
    #if func is None:
        #raise RuntimeError('Not running with the Werkzeug Server')
    #func()
    #return 'Server shutting down...'


@app.route('/startApp/<int:id>')
def startApp(id):
    '''启动应用'''
    server = master.appMap.get(id)
    if server is None:
        return _('serverNotExist')
    else:
        result = None
        if server.type != SERVER_GAME:
            with manage_app_permission.require():
                result = server.start()
        else:
            with manage_game_app_permission.require():
                result = server.start()
        if result == CONNECTION_REFUSED:
            errorMsg = _("RPCCallFail")
        else:
            errorMsg = None
        return redirect(url_for('index', errorMsg=errorMsg))



@app.route('/stopApp/<int:id>')
def stopApp(id):
    '''停止应用'''
    server = master.appMap.get(id)
    if server is None:
        return _('serverNotExist')
    else:
        result = None
        if server.type != 2:
            with manage_app_permission.require():
                result = server.stop()
        else:
            with manage_game_app_permission.require():
                result = server.stop()
        if result == CONNECTION_REFUSED:
            errorMsg = _("RPCCallFail")
        else:
            errorMsg = None
        return redirect(url_for('index', errorMsg=errorMsg))


@app.route('/vindicate/<int:id>')
@vindicate_game_permission.require()
def vindicate(id):
    '''维护游戏服'''
    server = master.appMap.get(id)
    if server is None:
        return _('serverNotExist')
     #检查应用当前状态
    if server.status == STATUS_RUN:
        return "游戏服正在运行中，请停服并同步完元宝后再进行维护程序"
    elif server.status == STATUS_VINDICATE:
        return "维护程序运行中，请勿运行同一游戏服维护程序的多个实例"
    result = server.vindicate()
    if result == CONNECTION_REFUSED:
        errorMsg = _("RPCCallFail")
    else:
        errorMsg = None
    return redirect(url_for('index', errorMsg=errorMsg))


@app.route('/changeSyncConfig/<int:serverId>/<int:status>')
@switch_sync_config_permission.require()
def changeSyncConfig(serverId, status):
    server = master.appMap.get(serverId)
    if server is None:
        return _('serverNotExist')
    if server.type != SERVER_LOGIN:
        return 'illegal operation!'
    if status != 0 and status != 2:
        return 'illegal status'
    server.switchSyncConfig(status)
    return redirect(url_for('index'))


@app.route('/consoleWall')
@view_console_permission.require()
def consoleWall():
    '''查看控制台日志'''
    apps = {}    
    category = session.get('category', 0)
    for app in master.appMap.values():
        if category == 0:
            apps[app.id] = app
        elif category == app.category:
            apps[app.id] = app
    logMap = {}    
    for app in apps.values():
        logMap[app.id] = app.getLogContent()        
    return render_template('consoleWall.html', logMap=logMap, appMap=apps, ajaxUrl=url_for('ajaxConsoleWall'))


@app.route('/ajaxConsoleWall')
@view_console_permission.require()
def ajaxConsoleWall():
    '''以json方式输出控制台日志'''
    apps = {}    
    category = session.get('category', 0)
    for app in master.appMap.values():
        if category == 0:
            apps[app.id] = app
        elif category == app.category:
            apps[app.id] = app
    logMap = {}    
    for app in apps.values():
        logMap[app.id] = app.getLogContent()    
    return jsonify(logMap=logMap)    


@app.route('/logConsole/<int:id>')
@view_console_permission.require()
def console(id):
    '''查看控制台日志'''
    app = master.appMap.get(id)
    if app is None:
        return _('serverNotExist')
    else:
        return render_template('console.html', log=app.getLogContent(), app=app, ajaxUrl=url_for('ajaxConsole', id=id))


@app.route('/errorLog/<int:id>')
@view_console_permission.require()
def getErrorLog(id):
    '''查看错误日志'''
    app = master.appMap.get(id)
    if app is None:
        return _('serverNotExist')
    else:
        return render_template('errorLog.html', errorLog=app.getErrorLog())


@app.route('/ajaxlogConsole/<int:id>')
@view_console_permission.require()
def ajaxConsole(id):
    '''以json方式输出控制台日志'''
    app = master.appMap.get(id)
    if app is None:
        return jsonify(log=_('serverNotExist'))
    else:
        return jsonify(log=app.getLogContent())


@app.route('/jar/<int:id>', methods=['GET', 'POST'])
@update_app_permission.require(http_exception=403)
def updateApp(id):
    '''更新程序'''
    gs = master.appMap.get(id)
    if gs is None:
        return _('serverNotExist')
    else:
        if request.method == 'GET':
            return render_template('jar.html', gs=gs)
        else:
            f = request.files['jar']
            if not f:
                return render_template('jar.html', gs=gs, errorMsg='请上传一个需要更新的程序包')
            else:
                if not f.filename.endswith('.jar'):
                    return render_template('jar.html', gs=gs, errorMsg="请传jar包")
                else:
                    try:
                        #先备份原程序
                        os.chdir(gs.path)
                        appendSuffix = datetime.datetime.now().strftime('_%Y%m%d_%H%M%S.')  # 默认文件备份后缀
                        fileName = gs.jar.split(".")[0]
                        fileSuffix = gs.jar.split(".")[-1]
                        bak = fileName + appendSuffix + fileSuffix
                        os.rename(gs.jar, bak)
                        f.save(os.path.join(gs.path, gs.jar))
                    except:
                        return render_template('jar.html', gs=gs, errorMsg="<font color=\"red\">" + str(sys.exc_info()[0]) + str(sys.exc_info()[1]) + "</font><br/>")
                    return render_template('jar.html', gs=gs, successMsg="更新成功")


@app.route('/updateScripts', methods=['GET', 'POST'])
@update_script_permission.require(http_exception=403)
def multyScriptUpdate():
    '''更新多个游戏服脚本'''
    gameServers = [appServer for appServer in master.appMap.values() if appServer.type == SERVER_GAME]
    if request.method == 'GET':
        return render_template('mscript.html', gameServers=gameServers)
    else:
        ids = request.form.getlist("id")
        if len(ids) == 0:
            return render_template('mscript.html', gameServers=gameServers, errorMsg=_("atLeastOneGameServerRequired"))
        gameServerArray = [appServerMap.get(int(id)) for id in ids]
        f = request.files['script']
        if not f:
            return render_template('mscript.html', gameServers=gameServers, errorMsg=_("noFileUploaded"))
        try:
            basePath = appPath
            path = os.path.join(basePath, 'uploads')
            os.chdir(path)
            folder = datetime.datetime.now().strftime('script_%Y%m%d_%H%M%S')
            os.mkdir(folder)
            path = os.path.join(path, folder)
            os.chdir(path)
            if f.filename.endswith(".7z"):
                f.save(os.path.join(path, 'scriptToUpdate.7z'))
                os.system('7z -y x \"scriptToUpdate.7z\" > /dev/null')
                os.remove('scriptToUpdate.7z')
            else:
                f.save(os.path.join(path, f.filename))
            return render_template('mscript.html', gameServers=gameServers, successMsg=wrapperUpdateGameScript(path, gameServerArray, False))
        except:
            return render_template('mscript.html', gameServers=gameServers, errorMsg="<font color=\"red\">" + str(sys.exc_info()[0]) + str(sys.exc_info()[1]) + "</font><br/>")
        finally:
            #无论最终成功与否都返回基目录
            os.chdir(basePath)
        return None


@app.route('/script/<int:id>', methods=['GET', 'POST'])
@update_script_permission.require(http_exception=403)
def updateGameScripts(id):
    '''更新游戏脚本'''
    gs = master.appMap.get(id)
    if gs is None:
        return render_template('script.html', gs=gs, errorMsg=_('serverNotExist'))
    else:
        if request.method == 'GET':
            return render_template('script.html', gs=gs)
        else:
            f = request.files['script']
            if not f:
                return render_template('script.html', gs=gs, errorMsg=_("noFileUploaded"))
            else:
                path = os.path.join(gs.path, 'scripts')
                if not os.path.exists(path):
                    os.mkdir(path)
                scriptFile = os.path.join(path, f.filename)
                if not (scriptFile.endswith('.7z') or scriptFile.endswith('.xls') or scriptFile.endswith('.wow')):
                    return render_template('script.html', gs=gs, errorMsg=_("unSupportedFileType"))
                f.save(scriptFile)
                #result = ""
                #如果是zip文件则解压缩
                if zipfile.is_zipfile(scriptFile):
                    zf = zipfile.ZipFile(scriptFile)
                    len(zf.namelist())
                    os.chdir(path)
                    zf.extractall()
                    zf.close()
                    os.remove(scriptFile)
                elif scriptFile.endswith('.7z'):
                    os.chdir(path)
                    os.system('7z -y x \"' + f.filename + '\" > /dev/null')
                    os.remove(scriptFile)
                #更新脚本文件
                return render_template('script.html', gs=gs, successMsg=wrapperUpdateGameScript(path, [gs], True))


def wrapperUpdateGameScript(srcPath, gameServerArray, isDeleteScript=False):
    #更新脚本文件
    #初始化需要更新的脚本列表
    scripts = []
    logger.info("--------------- 初始化需要更新的脚本列表 ---------------")
    result = "--------------- 初始化需要更新的脚本列表 ---------------<br/>"
    for f in os.listdir(srcPath):
        if os.path.isfile(os.path.join(srcPath, f)):
            logger.info(f)
            result += str(f) + "<br/>"
            scripts.append(f)
    logger.info("--------------- 总计有%d个脚本需要更新 -----------------", len(scripts))
    result += "--------------- 总计有" + str(len(scripts)) + "个脚本需要更新 -----------------<br/>"
    appendSuffix = datetime.datetime.now().strftime('_%Y%m%d_%H%M%S.')  # 默认文件备份后缀
    #循环更新指定游戏服脚本
    for gs in gameServerArray:
        result += "----------- 更新【" + gs.name + "】脚本 ---------------<br/>"
        result += updateScript(srcPath, scripts, gs.name, os.path.join(gs.path, 'data'), appendSuffix)
    if isDeleteScript:
        #删除更新成功的脚本
        logger.info("--------------- 删除更新成功的脚本 ---------------")
        result += "--------------- 删除更新成功的脚本 ---------------<br/>"
        for script in scripts:
            os.remove(srcPath + os.sep + script)
            logger.info("delete " + srcPath + os.sep + script)
            result += "delete " + srcPath + os.sep + script + "<br/>"
        logger.info("------------- 更新成功的脚本清除完毕 -------------")
        result += "------------- 更新成功的脚本清除完毕 -------------<br/>"
    result += "============= 脚本更新完成 ==============="
    return result


def updateScript(srcPath, scripts, gameServer, path, appendSuffix):
    '''
    更新脚本
    <参数>
            srcPath:更新源位置
            scripts:脚本列表
            gameServer:游戏服名
            path:游戏服data文件夹路径，如/home/project/game1/data
            appendSuffix:备份文件名后缀，一般为日期+时间
    <返回值>
            result:更新日志
    '''
    result = ""
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
                    #如果待更新的文件中有该文件则进行文件(hash)比较
            if filename in scripts:
                srcLastTime = time.strftime('%Y-%m-%d %X', time.localtime(os.path.getmtime(os.path.join(srcPath, filename))))
                targetLastTime = time.strftime('%Y-%m-%d %X', time.localtime(os.path.getmtime(os.path.join(dirpath, filename))))
                if hashFile(os.path.join(dirpath, filename)) != hashFile(os.path.join(srcPath, filename)):
                    #如果文件不同则备份并更新
                    try:
                        fileName = filename.split(".")[0]
                        fileSuffix = filename.split(".")[-1]
                        #备份文件名
                        bak = fileName + appendSuffix + fileSuffix
                        #切换到脚本所在目录
                        os.chdir(dirpath)
                        #备份原文件
                        os.rename(filename, bak)
                        #复制新的脚本文件到当前目录
                        shutil.copyfile(os.path.join(srcPath, filename), os.path.join(dirpath, filename))
                        logger.info("%25s %s %s %s %s", filename, srcLastTime, ">>>>>>", targetLastTime, os.path.join(dirpath, filename))
                        result += "{:<25s} {:s} >>>>>> {:s} {:s}".format(filename, srcLastTime, targetLastTime, os.path.join(path, filename)) + "<br/>"
                    except:
                        result += "<font color=\"red\">" + str(sys.exc_info()[0]) + str(sys.exc_info()[1]) + "</font><br/>"
                else:
                    #文件哈希值一致则只记录一下日志
                    logger.info("%25s %s %s %s %s", filename, srcLastTime, "======", targetLastTime, os.path.join(dirpath, filename))
                    result += "{:<25s} {:s} ====== {:s} {:s}<br/>".format(filename, srcLastTime, targetLastTime, os.path.join(dirpath, filename))
    return result


def getReadableSize(sizeInbyte):
    kb = sizeInbyte / 1024.0
    if kb < 1024:
        return '%.2fK' % kb
    mb = kb / 1024.0
    if mb < 1024:
        return '%.2fM' % mb
    gb = mb / 1024.0
    return '%.2fG' % gb


@app.route('/backupDb', methods=['GET', 'POST'])
@backup_database_permission.require()
def backupDatabase():
    backupPath = os.path.join(appPath, 'database')
    backupFiles = []
    for f in os.listdir(backupPath):
        if f == ".gitignore":
            continue
        size = getReadableSize(os.path.getsize(os.path.join(backupPath, f)))
        backupFiles.append((f, size))
    if request.method == 'GET':
        servers = []
        for server in appServerMap.values():
            if server.type == 1 or type == 2:
                servers.append(server)
        return render_template('backupDb.html', servers=servers, backupFiles=backupFiles)
    idList = request.form.getlist('id')
    if len(idList) == 0:
        return jsonify(msg=_('noServerSelected'))
    servers = []
    for id in idList:
        server = appServerMap.get(int(id))
        if server is None:
            return jsonify(msg=_('illegalServerId'))
        servers.append(server)
    #开始备份数据库
    appendSuffix = datetime.datetime.now().strftime('_%Y%m%d_%H%M%S.sql')  # 默认文件备份后缀
    for server in servers:
        print '备份' + server.name + '数据库开始...'
        cmd = "mysqldump -u" + server.dbUser + " -p'" + server.dbPassword + "' --port=" + str(server.dbPort) + " --skip-lock-tables --default-character-set=utf8 -h " + server.dbHost + " " + server.mainDb + " > " + os.path.join(backupPath, server.mainDb + appendSuffix)
        print '备份主库...'
        os.system(cmd)
        cmd = "mysqldump -u" + server.dbUser + " -p'" + server.dbPassword + "' --port=" + str(server.dbPort) + " --skip-lock-tables --default-character-set=utf8 -h " + server.dbHost + " " + server.statDb + " > " + os.path.join(backupPath, server.statDb + appendSuffix)
        print '备份统计库...'
        os.system(cmd)
        os.system(cmd)
        print '备份' + server.name + '数据库完毕'
    return jsonify(msg=_('backupSuccess'))


def hashFile(filePath):
    '''
    计算指定文件路径的hash值
    '''
    if os.path.exists(filePath) and os.path.isfile(filePath):
        sha1obj = hashlib.sha1()
        f = open(filePath)
        try:
            for line in f:
                sha1obj.update(line)
        finally:
            f.close()
        '''
        with open(filePath, 'rb') as f:
            sha1obj = hashlib.sha1()
            sha1obj.update(f.read())
        '''
    return sha1obj.hexdigest()




def getProcessIdByAppName(appName):
    '''根据应用名来获取程序的进程编号'''
    pid = -1
    cmd = "ps aux | grep " + appName + " | grep -v grep | awk '{print $2}'| tr -d '\n'"
    output = subprocess.check_output(["/bin/bash", "-c", cmd])
    if len(output) > 0:
        pid = int(output)
    return pid


def loadConfig():
    '''加载配置'''
    #权限配置
    global httpPort, master, userMap, categoryMap
    config = "config.xml"
    logger.info("load config...")
    dom = xml.dom.minidom.parse(config)
    root = dom.documentElement
    '''
    agentList = []
    for agentNode in root.getElementsByTagName('agent'):
        ip = agentNode.getAttribute('ip')
        port = int(agentNode.getAttribute('port'))
        agentList.append((ip, port))
    master = Master(agentList)
    '''
    httpPort = int(root.getAttribute('httpPort'))
    master = Master(int(root.getAttribute('masterPort')))
    master.start()
    for node in root.getElementsByTagName('categories')[0].getElementsByTagName('category'):
        id = int(node.getAttribute('id'))
        name = node.getAttribute('name')
        categoryMap[id] = name
    for roleNode in root.getElementsByTagName('role'):
        key = roleNode.getAttribute('key')
        #roleName = roleNode.getAttribute('name')
        userRoleMap[key] = list()
        rolePermissionMap[key] = list()
        for userNode in roleNode.getElementsByTagName('users')[0].getElementsByTagName('user'):
            userName = userNode.getAttribute('name')
            userPassword = userNode.getAttribute('password')
            userMap[userName] = userPassword
            userRoleMap.get(key).append(userName)
        for actionNode in roleNode.getElementsByTagName('actions')[0].getElementsByTagName('action'):
            rolePermissionMap.get(key).append(actionNode.childNodes[0].data)


def initLogger():
    '''
    初始化日志配置
    '''
    logger = logging.getLogger("goss")
    fileHandler = logging.FileHandler('gossMaster.log')
    streamHandler = logging.StreamHandler()
    fmt = logging.Formatter("%(asctime)s, %(message)s")
    fileHandler.setFormatter(fmt)
    streamHandler.setFormatter(fmt)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(fileHandler)
    logger.addHandler(streamHandler)
    return logger

if __name__ == '__main__':
    reload(sys)
    sys.setdefaultencoding('utf-8')
    logger = initLogger()
    loadConfig()
    app.run(host='0.0.0.0', port=httpPort, debug=True, use_reloader=False)


