#!/usr/bin/env python
#encoding=utf-8

import sys
import os
import datetime
import logging
import hashlib
import xml.dom.minidom

from flask import Flask, render_template, send_from_directory, request, redirect, url_for, session, jsonify
from flask.ext.principal import Principal, Permission, ActionNeed, TypeNeed, Identity, identity_changed, PermissionDenied
from flaskext.babel import Babel, gettext as _
from jinja2 import environmentfilter

from gossMaster import Master
from constants import SUCCESS, SERVER_GAME, SERVER_LOGIN, CONNECTION_REFUSED, STATUS_RUN, STATUS_VINDICATE


#web监听端口
httpPort = 9999
#分类
categoryMap = {}
#应用部署路径
appPath = os.path.dirname(os.path.abspath(__file__))
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
    #随机32位足够复杂的secret key
    SECRET_KEY=os.urandom(32).encode('hex')
)
#装载认证扩展
principals = Principal(app)
##########权限配置##########
update_script_permission = Permission(ActionNeed('update_script'))
update_app_permission = Permission(ActionNeed('update_app'))
vindicate_game_permission = Permission(ActionNeed('vindicate_game'))
view_console_permission = Permission(ActionNeed('view_console'))
view_agent_permission = Permission(ActionNeed('view_agent'))
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

@environmentfilter
def datetimeformat(value, format='%H:%M %d-%m-%Y'):
    '''日期格式化filter'''
    return value.strftime(format)


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
    '''首页(检查各服状态)'''
    #刷新应用状态
    master.refreshAppStatusList()
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
    logMap = {}
    for app in filterAppsByCategory().values():
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


@app.route('/agentStatus')
@view_agent_permission.require()
def agentStatus():
    '''查看agent状态'''
    theMap = {}
    now = datetime.datetime.now()
    for ip, data in master.statusMap.items():
        theData = [] + data
        theData.append(now - data[0])
        theMap[ip] = theData
    return render_template('agent.html', agentStatusMap=theMap, appMap=master.appMap)


def parseAppUpdateResult(result):
    '''解析应用更新结果'''
    msg = ""
    for key, value in result.items():
        for id, code in value:
            name = master.appMap[id].name
            if code == SUCCESS:
                msg += key + "  " + name + "  更新成功<br/>"
            else:
                msg += key + "  " + name + "  更新失败<br/>"
    return msg


@app.route('/updateApps', methods=['GET', 'POST'])
@update_app_permission.require(http_exception=403)
def updateMultyApps():
    '''更新多个应用程序'''
    if request.method == 'GET':
        return render_template('mjar.html', gameServers=filterAppsByCategory().values())
    else:
        f = request.files['jar']
        if not f:
            return render_template('mjar.html', gameServers=master.appMap.values(), errorMsg='请上传一个需要更新的程序包')
        else:
            if not f.filename.endswith('.jar'):
                return render_template('mjar.html', gameServers=master.appMap.values(), errorMsg="请传jar包")
            else:
                ids = request.form.getlist("id")
                if len(ids) == 0:
                    return render_template('mjar.html', gameServers=master.appMap.values(), errorMsg=_("atLeastOneGameServerRequired"))
                else:
                    #将id转为int
                    ids = map(lambda x: int(x), ids)
                try:
                    basePath = appPath
                    path = os.path.join(basePath, 'uploads')
                    fileName = datetime.datetime.now().strftime('app_%Y%m%d_%H%M%S.jar')
                    appJar = os.path.join(path, fileName)
                    f.save(appJar)
                    f.close()
                    f = open(appJar, "rb")
                    result = master.updateApps(ids, fileName, f.read())
                    f.close()
                except:
                    return render_template('mjar.html', gameServers=master.appMap.values(), errorMsg=str(sys.exc_info()[0]) + str(sys.exc_info()[1]))
                return render_template('mjar.html', gameServers=master.appMap.values(), infoMsg=parseAppUpdateResult(result))


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
                        basePath = appPath
                        path = os.path.join(basePath, 'uploads')
                        fileName = datetime.datetime.now().strftime('app_%Y%m%d_%H%M%S.jar')
                        appJar = os.path.join(path, fileName)
                        f.save(appJar)
                        f.close()
                        f = open(appJar, "rb")
                        result = master.updateApps([id, ], fileName, f.read())
                        f.close()
                    except:
                        return render_template('jar.html', gs=gs, errorMsg=str(sys.exc_info()[0]) + str(sys.exc_info()[1]))
                    return render_template('jar.html', gs=gs, infoMsg=parseAppUpdateResult(result))


def parseScriptUpdateResult(result):
    '''解析脚本更新结果'''
    #result格式：key-agent ip value-([(应用编号, 需要更新的脚本数, 成功更新的脚本数),], 更新日志)
    msg = ""
    logStr = ""
    for key, value in result.items():
        logStr += "=========【" + key + "】更新结果==========<br/>" + value[1]
        for id, scriptsCount, successCount in value[0]:
            name = master.appMap[id].name
            if scriptsCount == successCount:
                msg += key + "  " + name + "  更新成功<br/>"
            else:
                failCount = scriptsCount - successCount
                msg += key + "  " + name + "  " + str(failCount) + "个脚本更新失败<br/>"
    return msg + logStr


@app.route('/updateScripts', methods=['GET', 'POST'])
@update_script_permission.require(http_exception=403)
def multyScriptUpdate():
    '''更新多个游戏服脚本'''
    gameServers = [appServer for appServer in filterAppsByCategory().values() if appServer.type == SERVER_GAME]
    if request.method == 'GET':
        return render_template('mscript.html', gameServers=gameServers)
    else:
        ids = request.form.getlist("id")
        if len(ids) == 0:
            return render_template('mscript.html', gameServers=gameServers, errorMsg=_("atLeastOneGameServerRequired"))
        else:
            #将id转为int
            ids = map(lambda x: int(x), ids)
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
            fileName = f.filename
            f.save(os.path.join(path, fileName))
            f.close()
            f = open(os.path.join(path, fileName), "rb")
            result = master.updateScripts(ids, fileName, f.read())
            f.close()
            return render_template('mscript.html', gameServers=gameServers, infoMsg=parseScriptUpdateResult(result))
        except:
            return render_template('mscript.html', gameServers=gameServers, errorMsg="<font color=\"red\">" + str(sys.exc_info()[0]) + str(sys.exc_info()[1]) + "</font><br/>")
        finally:
            #无论最终成功与否都返回基目录
            os.chdir(basePath)
        return None


@app.route('/script/<int:id>', methods=['GET', 'POST'])
@update_script_permission.require(http_exception=403)
def updateGameScripts(id):
    '''更新单个游戏脚本'''
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
                basePath = appPath
                path = os.path.join(basePath, 'uploads')
                os.chdir(path)
                folder = datetime.datetime.now().strftime('script_%Y%m%d_%H%M%S')
                os.mkdir(folder)
                path = os.path.join(path, folder)
                os.chdir(path)
                fileName = f.filename
                f.save(os.path.join(path, fileName))
                f.close()
                f = open(os.path.join(path, fileName), "rb")
                result = master.updateScripts([id], fileName, f.read())
                f.close()
                return render_template('script.html', gs=gs, infoMsg=parseScriptUpdateResult(result))


@app.route('/backupDb', methods=['GET', 'POST'])
@backup_database_permission.require()
def backupDatabase():
    if request.method == 'GET':
        backupMap = master.getDatabaseBackupMap()
        servers = []
        for server in filterAppsByCategory().values():
            if server.type == SERVER_LOGIN or server.type == SERVER_GAME:
                servers.append(server)
        return render_template('backupDb.html', appMap=master.appMap, servers=servers, backupMap=backupMap, queueMap=master.backupQueueMap)
    idList = request.form.getlist('id')
    if len(idList) == 0:
        return jsonify(msg=_('noServerSelected'))
    else:
        #将id转为int
        idList = map(lambda x: int(x), idList)

    for id in idList:
        server = master.appMap.get(id)
        if server is None:
            return jsonify(msg=_('illegalServerId'))
    batchId = datetime.datetime.now().strftime('db_%Y%m%d_%H%M%S')
    master.backupDatabase(batchId, idList)
    return jsonify(msg=_('backupOrderSent'))


def filterAppsByCategory():
    '''根据session中的分类来返回指定分类的应用'''
    apps = {}
    category = session.get('category', 0)
    for app in master.appMap.values():
        if category == 0:
            apps[app.id] = app
        elif category == app.category:
            apps[app.id] = app
    return apps


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
