from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import json

@register("context_manager", "Developer", "管理对话上下文的插件", "1.0.0")
class ContextManagerPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
    
    @filter.command("roll")
    async def roll_context(self, event: AstrMessageEvent):
        """回滚到上一条消息并重新请求LLM"""
        try:
            # 获取当前对话
            uid = event.unified_msg_origin
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(uid)
            
            if not curr_cid:
                yield event.plain_result("没有找到当前对话")
                return
            
            conversation = await self.context.conversation_manager.get_conversation(uid, curr_cid)
            history = json.loads(conversation.history) if conversation.history else []
            
            # 查找最后一条AI回复
            ai_response_index = None
            for i in range(len(history) - 1, -1, -1):
                if history[i].get("role") == "assistant":
                    ai_response_index = i
                    break
            
            if ai_response_index is None:
                yield event.plain_result("没有找到AI的回复")
                return
            
            # 删除最后一条AI回复
            removed_ai_response = history.pop(ai_response_index)
            
            # 保存修改后的历史记录 - 明确传递 conversation_id 和 history
            await self.context.conversation_manager.update_conversation(
                conversation_id=conversation.id,  # 使用 conversation.id 作为 conversation_id
                history=json.dumps(history)  # 序列化后的历史记录
            )
            
            # 获取最后一条用户消息作为新的提示
            user_messages = [msg for msg in history if msg.get("role") == "user"]
            if not user_messages:
                yield event.plain_result("没有找到用户消息")
                return
            
            last_user_message = user_messages[-1].get("content", "")
            
            # 重新请求LLM
            func_tools_mgr = self.context.get_llm_tool_manager()
            yield event.request_llm(
                prompt=last_user_message,
                func_tool_manager=func_tools_mgr,
                contexts=history,
                conversation=conversation
            )
            
        except Exception as e:
            logger.error(f"roll_context error: {str(e)}")
            yield event.plain_result(f"执行回滚时发生错误: {str(e)}")
    
    @filter.command("dellast")
    async def delete_last_interaction(self, event: AstrMessageEvent):
        """删除最后一条AI回复和对应的用户指令"""
        try:
            # 获取当前对话
            uid = event.unified_msg_origin
            curr_cid = await self.context.conversation_manager.get_curr_conversation_id(uid)
            
            if not curr_cid:
                yield event.plain_result("没有找到当前对话")
                return
            
            conversation = await self.context.conversation_manager.get_conversation(uid, curr_cid)
            history = json.loads(conversation.history) if conversation.history else []
            
            # 查找最后一条交互（AI回复和对应的用户消息）
            ai_response_index = None
            user_message_index = None
            
            for i in range(len(history) - 1, -1, -1):
                if history[i].get("role") == "assistant" and ai_response_index is None:
                    ai_response_index = i
                elif history[i].get("role") == "user" and user_message_index is None and ai_response_index is not None:
                    user_message_index = i
                    break
            
            if ai_response_index is None:
                yield event.plain_result("没有找到AI的回复")
                return
            
            if user_message_index is None:
                yield event.plain_result("没有找到对应的用户消息")
                return
            
            # 删除AI回复和用户消息
            # 先删除索引较大的，以免影响索引
            if ai_response_index > user_message_index:
                history.pop(ai_response_index)
                history.pop(user_message_index)
            else:
                history.pop(user_message_index)
                history.pop(ai_response_index)
            
            # 保存修改后的历史记录 - 明确传递 conversation_id 和 history
            await self.context.conversation_manager.update_conversation(
                conversation_id=conversation.id,  # 使用 conversation.id 作为 conversation_id
                history=json.dumps(history)  # 序列化后的历史记录
            )
            
            yield event.plain_result("已成功删除最后一条交互")
            
        except Exception as e:
            logger.error(f"delete_last_interaction error: {str(e)}")
            yield event.plain_result(f"执行删除时发生错误: {str(e)}")
    
    async def terminate(self):
        """插件终止时调用"""
        logger.info("ContextManagerPlugin 已终止")
