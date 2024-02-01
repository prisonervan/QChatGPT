from __future__ import annotations

import typing
import time

import mirai

from .. import handler
from ... import entities
from ....core import entities as core_entities
from ....provider import entities as llm_entities
from ....plugin import events


class ChatMessageHandler(handler.MessageHandler):

    async def handle(
        self,
        query: core_entities.Query,
    ) -> typing.AsyncGenerator[entities.StageProcessResult, None]:
        """处理
        """
        # 取session
        # 取conversation
        # 调API
        #   生成器

        # 触发插件事件
        event_class = events.PersonNormalMessageReceived if query.launcher_type == core_entities.LauncherTypes.PERSON else events.GroupNormalMessageReceived

        event_ctx = await self.ap.plugin_mgr.emit_event(
            event=event_class(
                launcher_type=query.launcher_type.value,
                launcher_id=query.launcher_id,
                sender_id=query.sender_id,
                text_message=str(query.message_chain),
                query=query
            )
        )

        if event_ctx.is_prevented_default():
            if event_ctx.event.reply is not None:
                query.resp_message_chain = mirai.MessageChain(event_ctx.event.reply)

                yield entities.StageProcessResult(
                    result_type=entities.ResultType.CONTINUE,
                    new_query=query
                )
            else:
                yield entities.StageProcessResult(
                    result_type=entities.ResultType.INTERRUPT,
                    new_query=query
                )
        else:

            if event_ctx.event.alter is not None:
                query.message_chain = mirai.MessageChain([
                    mirai.Plain(event_ctx.event.alter)
                ])

            session = await self.ap.sess_mgr.get_session(query)

            conversation = await self.ap.sess_mgr.get_conversation(session)

            # =========== 触发事件 PromptPreProcessing

            event_ctx = await self.ap.plugin_mgr.emit_event(
                event=events.PromptPreProcessing(
                    session_name=f'{session.launcher_type.value}_{session.launcher_id}',
                    default_prompt=conversation.prompt.messages,
                    prompt=conversation.messages,
                    query=query
                )
            )

            conversation.prompt.messages = event_ctx.event.default_prompt
            conversation.messages = event_ctx.event.prompt

            conversation.messages.append(
                llm_entities.Message(
                    role="user",
                    content=str(query.message_chain)
                )
            )

            text_length = 0

            start_time = time.time()

            async for result in conversation.use_model.requester.request(query, conversation):
                query.resp_messages.append(result)

                if result.content is not None:
                    text_length += len(result.content)

                yield entities.StageProcessResult(
                    result_type=entities.ResultType.CONTINUE,
                    new_query=query
                )

            await self.ap.ctr_mgr.usage.post_query_record(
                session_type=session.launcher_type.value,
                session_id=str(session.launcher_id),
                query_ability_provider="QChatGPT.Chat",
                usage=text_length,
                model_name=conversation.use_model.name,
                response_seconds=int(time.time() - start_time),
                retry_times=-1,
            )