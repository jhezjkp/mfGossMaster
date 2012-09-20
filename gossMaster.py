#!/usr/bin/env python
#encoding=utf-8

'''
goss中控
'''

import sys
import time
import logging
import threading
import xmlrpclib
import socket
import base64
from SimpleXMLRPCServer import SimpleXMLRPCServer

from constants import *

class AppNode(object):
	'''应用节点'''

	def __init__(self, id, name, category, host, type, status, configStatus, client):		
		self.id = id
		self.name = name
		self.category = category
		self.host = host
		self.type = type
		self.status = status
		self.configStatus = configStatus
		self.client = client
		self.logger = logging.getLogger("goss.rpc")

	def start(self):
		'''启动应用'''
		result = SUCCESS
		try:
			self.client.startApp(self.id)
		except socket.error:
			self.logger.error(socket.error)
			result = CONNECTION_REFUSED
		return result

	def stop(self):
		'''停止应用'''
		result = SUCCESS
		try:
			self.client.stopApp(self.id)
		except socket.error:
			self.logger.error(socket.error)
			result = CONNECTION_REFUSED
		return result		

	def vindicate(self):
		'''运行维护程序'''
		result = SUCCESS
		if self.type != SERVER_GAME or self.status != STATUS_STOP:
		    result = ILEGAL_OPERATE
		else:
			try:
				self.client.vindicate(self.id)
			except socket.error:
				self.logger.error(socket.error)
				result = CONNECTION_REFUSED
		return result

	def switchSyncConfig(self, configStatus):
		'''切换同步配置'''
		if self.type != SERVER_LOGIN:
			return ILEGAL_OPERATE
		result = SUCCESS
		try:
			if self.client.switchSyncConfig(self.id, configStatus) == SUCCESS:
				self.configStatus = configStatus
		except socket.error:
			self.logger.error(socket.error)
			result = CONNECTION_REFUSED
		return result

	def getLogContent(self):
		'''获取控制台日志内容'''
		try:			
			logContent = base64.b64decode(self.client.getConsoleLog(self.id)[1])			
		except socket.error:
			logContent = "RPC Call failed..."
			self.logger.error(socket.error)
			result = CONNECTION_REFUSED
		return logContent

	def getErrorLog(self):
		'''获取错误日志'''
		try:
			logContent = self.client.getErrorLog(self.id)[1]
			logContent = base64.b64decode(logContent)
		except socket.error:
			logContent = "RPC Call failed..."
			self.logger.error(socket.error)
			result = CONNECTION_REFUSED
		return logContent
	

class Master(threading.Thread):
	'''goss中控'''

	#agentMap key-ip value-client
	agentMap = {}	
	#应用map key-id value-AppNode
	appMap = {}	

	def __init__(self, masterPort):
		super(Master, self).__init__()
		self.logger = logging.getLogger("goss.master")
		self.masterPort = masterPort		
		#确保主线程退出时，本线程也退出        
		self.daemon = True

	def register(self, ip, port, apps):
		'''注册应用'''		
		#agent
		client = xmlrpclib.ServerProxy("http://" + ip + ":" + str(port), encoding='utf-8')
		self.agentMap[ip] = client
		self.logger.info("register agent 【%s】", ip + ":" + str(port))
		#先把旧应用的移除
		for app in self.appMap.values():
			if app.host == ip:
				del self.appMap[app.id]
				self.logger.debug("remove app 【%s】", app.name)
		#再把新应用的加上
		for id, name, category, type, status, configStatus in apps:
			appNode = AppNode(id, name, category, ip, type, status, configStatus, client)
			self.appMap[id] = appNode
			self.logger.info("register app 【%s】", name)			
		return SUCCESS

	def updateAppStatus(self, ip, port, statusTupleList):		
		if ip not in self.agentMap:
			self.logger.error("agent 【%s】 not registered yet...", ip + ":" + str(port))
			return AGENT_NOT_REGISTER
		for statusTuple in statusTupleList:
			id = statusTuple[0]
			status = statusTuple[1]
			configStatus = statusTuple[2]
			if id in self.appMap:
				app = self.appMap[id]
				app.status = status
				app.configStatus = configStatus
			else:
				self.logger.error("app(id=%d) not registered yet...", id)
				return AGENT_NOT_REGISTER
		return SUCCESS

	def run(self):
		server = SimpleXMLRPCServer(("0.0.0.0", self.masterPort), allow_none=True, logRequests=False)
		self.logger.info("Listening on port %d ...", self.masterPort)
		server.register_function(self.register, "register")
		server.register_function(self.updateAppStatus, "updateAppStatus")
		server.serve_forever() 

