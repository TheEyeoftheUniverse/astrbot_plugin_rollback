import json
from typing import List, Dict
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("conversation_manager", "TEOTU", "rollback", "1.0.0")
class ConversationManagerPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
    
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
            
            # 查找最后一条用户消息
            last_user_msg = None
            last_user_index = -1
            for i in range(len(history)-1, -1, -1):
                if history[i]["role"] == "user":
                    last_user_msg = history[i]["content"]
                    last_user_index = i
                    break
            
            if not last_user_msg:
                yield event.plain_result("未找到用户消息")
                return
            
            # 删除这条用户消息之后的所有消息（包括助手回复）
            truncated_history = history[:last_user_index]
            
            # 更新对话历史
            await self.context.conversation_manager.update_conversation(uid, curr_cid, truncated_history)
            
            # 重新请求LLM - 使用底层API调用以便获取响应
            provider = self.context.get_using_provider()
            if not provider:
                yield event.plain_result("未找到可用的LLM提供商")
                return
            
            # 使用底层API调用LLM
            llm_response = await provider.text_chat(
                prompt=last_user_msg,
                session_id=curr_cid,
                contexts=truncated_history,
                func_tool=self.context.get_llm_tool_manager(),
                system_prompt=getattr(conversation, 'system_prompt', "") or ""
            )
            
            # 处理LLM响应
            if llm_response.role == "assistant":
                # 手动发送LLM回复
                yield event.plain_result(llm_response.completion_text)
                
                # 更新对话历史，添加用户消息和助手回复
                new_history = truncated_history + [
                    {"role": "user", "content": last_user_msg},
                    {"role": "assistant", "content": llm_response.completion_text}
                ]
                await self.context.conversation_manager.update_conversation(uid, curr_cid, new_history)
            elif llm_response.role == "tool":
                # 处理函数调用
                yield event.plain_result(f"触发了函数调用: {llm_response.tools_call_name}")
            else:
                yield event.plain_result("LLM响应格式未知")
            
        except Exception as e:
            logger.error(f"roll命令执行错误: {str(e)}")
            yield event.plain_result(f"执行失败: {str(e)}")
    
    @filter.command("dellast")
    async def delete_last_interaction(self, event: AstrMessageEvent):
        """删除最后一组用户-助手交互"""
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
            
            # 查找最后一组完整的交互（用户消息+助手回复）
            last_user_index = -1
            for i in range(len(history)-1, -1, -1):
                if history[i]["role"] == "user":
                    last_user_index = i
                    break
            
            if last_user_index == -1:
                yield event.plain_result("未找到用户消息")
                return
            
            # 删除从最后一条用户消息开始的所有记录
            new_history = history[:last_user_index]
            
            # 更新对话历史
            await self.context.conversation_manager.update_conversation(uid, curr_cid, new_history)
            
            yield event.plain_result("已删除最后一组对话记录")
            
        except Exception as e:
            logger.error(f"dellast命令执行错误: {str(e)}")
            yield event.plain_result(f"执行失败: {str(e)}")
    
    async def terminate(self):
        """插件终止时调用"""
        pass
