import json
import time
import re
from typing import List, Dict
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("rollback", "TEOTU", "重新请求llm回复最后一条用户消息或删除最后一组对话记录的插件", "1.0.0")
class ConversationManagerPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 存储roll操作的状态
        self.roll_states = {}
    
    def extract_clean_message(self, content):
        """从消息内容中提取干净的消息文本，移除 [User ID: Nickname:] 元数据"""
        # 匹配 [User ID:.*?Nickname:.*?] 格式的元数据
        pattern = r'\[User ID:.*?Nickname:.*?\](.*)'
        match = re.search(pattern, content, re.DOTALL)
        
        if match:
            return match.group(1).strip()
        
        # 如果没有匹配到元数据格式，返回原始内容
        return content
    
    def find_last_interaction(self, history):
        """查找最后一次交互的用户消息和助手回复的索引"""
        last_user_index = -1
        last_assistant_index = -1
        
        for i in range(len(history)-1, -1, -1):
            if history[i]["role"] == "assistant" and last_assistant_index == -1:
                last_assistant_index = i
            elif history[i]["role"] == "user" and last_user_index == -1:
                last_user_index = i
                break
        
        return last_user_index, last_assistant_index
    
    def delete_last_interaction(self, history, last_user_index, last_assistant_index):
        """删除最后一次交互"""
        if last_assistant_index != -1 and last_assistant_index > last_user_index:
            # 删除助手回复和用户消息
            return history[:last_user_index]
        else:
            # 没有找到助手回复，只删除用户消息
            return history[:last_user_index]
    
    @filter.command("roll")
    async def roll_last_message(self, event: AstrMessageEvent):
        """重新请求LLM回复最后一条用户消息"""
        try:
            # 获取当前会话和对话ID
            uid = event.unified_msg_origin
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(uid)
            
            if not curr_cid:
                yield event.plain_result("当前没有活跃的对话")
                return
            
            # 获取对话对象和历史记录
            conversation = await self.context.conversation_manager.get_conversation(uid, curr_cid)
            history = json.loads(conversation.history) if conversation and conversation.history else []
            
            if not history:
                yield event.plain_result("对话历史为空")
                return
            
            # 查找最后一次交互
            last_user_index, last_assistant_index = self.find_last_interaction(history)
            
            if last_user_index == -1:
                yield event.plain_result("未找到用户消息")
                return
            
            # 提取干净的消息内容（移除元数据）
            last_user_msg = history[last_user_index]["content"]
            clean_user_msg = self.extract_clean_message(last_user_msg)
            
            # 删除最后一次交互
            new_history = self.delete_last_interaction(history, last_user_index, last_assistant_index)
            
            # 更新对话历史
            await self.context.conversation_manager.update_conversation(uid, curr_cid, new_history)
            
            # 获取更新后的对话对象
            updated_conversation = await self.context.conversation_manager.get_conversation(uid, curr_cid)
            
            # 存储roll操作的状态
            roll_key = f"{uid}_{curr_cid}"
            self.roll_states[roll_key] = {
                "clean_user_msg": clean_user_msg,
                "conversation": updated_conversation,
            }
            
            logger.info(f"Roll操作: 重新请求最后一条用户消息")
            
            # 使用AstrBot的事件系统触发完整的LLM处理流程
            yield event.request_llm(
                prompt=clean_user_msg,
                session_id=curr_cid,
                conversation=updated_conversation
            )
            
        except Exception as e:
            logger.error(f"roll命令执行错误: {str(e)}")
            yield event.plain_result(f"执行失败: {str(e)}")
    
    @filter.on_llm_request(priority=999)
    async def handle_roll_llm_request(self, event: AstrMessageEvent, req):
        """处理roll操作的LLM请求"""
        uid = event.unified_msg_origin
        curr_cid = await self.context.conversation_manager.get_curr_conversation_id(uid)
        
        if not curr_cid:
            return
        
        roll_key = f"{uid}_{curr_cid}"
        if roll_key in self.roll_states:
            # 这是一个roll操作，确保使用清理后的消息内容
            roll_state = self.roll_states[roll_key]
            req.prompt = roll_state["clean_user_msg"]
    
    @filter.command("dellast")
    async def delete_last_interaction_cmd(self, event: AstrMessageEvent):
        """删除最后一组对话记录"""
        try:
            # 获取当前会话和对话ID
            uid = event.unified_msg_origin
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(uid)
            
            if not curr_cid:
                yield event.plain_result("当前没有活跃的对话")
                return
            
            # 获取对话对象和历史记录
            conversation = await self.context.conversation_manager.get_conversation(uid, curr_cid)
            history = json.loads(conversation.history) if conversation and conversation.history else []
            
            if not history:
                yield event.plain_result("对话历史为空")
                return
            
            # 查找最后一次交互
            last_user_index, last_assistant_index = self.find_last_interaction(history)
            
            if last_user_index == -1:
                yield event.plain_result("未找到用户消息")
                return
            
            # 删除最后一次交互
            new_history = self.delete_last_interaction(history, last_user_index, last_assistant_index)
            
            # 更新对话历史
            await self.context.conversation_manager.update_conversation(uid, curr_cid, new_history)
            
            logger.info(f"删除最后一组对话记录")
            
            yield event.plain_result("已删除最后一组对话记录")
            
        except Exception as e:
            logger.error(f"dellast命令执行错误: {str(e)}")
            yield event.plain_result(f"执行失败: {str(e)}")
    
    async def terminate(self):
        """插件终止时调用"""
        # 清理所有roll状态
        self.roll_states.clear()
