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
        
        # 保存修改后的历史记录
        await self.context.conversation_manager.update_conversation(
            conversation_id=curr_cid,
            history=json.dumps(history),
            unified_msg_origin=uid
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
