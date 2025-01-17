"""Imports"""
import discord
import requests
from discord.ext import commands
from main import BotStartTime, scheduler
from loggerfile import logger
from cogs._helpers import SABNZBD_ENDPOINT, humantime, sudo_check, NZBHYDRA_URL_ENDPOINT, remove_private_stuff, embed
import httpx
import psutil
import time
import datetime
import re
import aiofiles
from cogs._config import *
from cachetools import TTLCache
import asyncio

downloading_status_msgids = {}
sabnzbd_pack_category = "pack"
# cache user and sabid for 30 mins
sabnzbd_userid_log = TTLCache(maxsize=128, ttl=30 * 60)


class UsenetHelper:
    def __init__(self) -> None:
        self.SABNZBD_API = f"{SABNZBD_ENDPOINT}&output=json"
        self.client = httpx.AsyncClient(timeout=20)

    def footer_message(self):  # TODO speed calc for footer
        # calculating system speed per seconds.
        # net_io_counters = psutil.net_io_counters()
        # bytes_sent = net_io_counters.bytes_sent
        # bytes_recv = net_io_counters.bytes_recv

        # time.sleep(1)

        # net_io_counters = psutil.net_io_counters()
        # download_speed = net_io_counters.bytes_recv - bytes_recv
        # upload_speed = net_io_counters.bytes_sent - bytes_sent

        botuptime = humantime(
            (datetime.datetime.utcnow()-BotStartTime).total_seconds())
        # msg = f"🟢 DL: {humanbytes(download_speed)}/s 🟡 UL: {humanbytes(upload_speed)}/s | ⌚ Uptime: {botuptime}"
        msg = f"⌚ Uptime: {botuptime}"
        return msg

    def show_progress_still(self, percent: int, width: int = 20):
        int_percent = round(percent)
        hashblocks = round((int_percent*width/100)-1)
        if hashblocks < 0:
            hashblocks = 0
        return "▰" * hashblocks + "▱" * (width-hashblocks-1)
        # return "#️⃣"* hashblocks + "▶️" + "🟦"*(width-hashblocks-1) + "🏁"

    async def downloading_status_page(self):
        """Generate status page for progress message."""

        try:
            downloading_response = await self.client.get(
                self.SABNZBD_API, params={"mode": "queue"})
            # print(downloading_response.json())
            downloading_queue_list = downloading_response.json()[
                "queue"]["slots"]
        except:
            downloading_queue_list = []

        try:
            # print(1)
            postprocessing_response = await self.client.get(
                self.SABNZBD_API, params={"mode": "history"})
            # print(postprocessing_response.json()["history"]["slots"])
            postprocessing_queue_list = [
                slot
                for slot in postprocessing_response.json()["history"]["slots"]
                if slot["status"] not in ["Completed", "Failed"]]
            postprocessing_queue_list.reverse()
        except:
            postprocessing_queue_list = []

        # status_page = ""

        status_embed = discord.Embed(title="📊 Status", color=discord.Color.green(
        ), timestamp=datetime.datetime.utcnow())
        status_embed.description = ''

        if downloading_queue_list:
            speedString = downloading_response.json()["queue"]["speed"].replace(
                "B", " B/s").replace("K", " KB/s").replace("M", " MB/s")
            status_embed.description = f'**Downloading @ {speedString}**\n\n'

            for index, queue in enumerate(downloading_queue_list):
                file_name = queue["filename"]
                if re.search(r"(http|https)", file_name):
                    file_name = "Adding file from ID."
                if postprocessing_queue_list:
                    status_embed.description += f'**🗂 FileName:** `{file_name}`\n' \
                        f"**Status:** *Queued*\n" \
                        f"**Task ID:** `{queue['nzo_id']}`\n━━━━━━━━━━━━━━━━━━━━\n"
                elif queue["index"] == 0:
                    status_embed.description += f'**🗂 FileName:** `{file_name}`\n{self.show_progress_still(int(queue["percentage"]))} {queue["percentage"]}%\n' \
                                                f"**{queue['sizeleft']}** remaining of **{queue['size']}**\n" \
                                                f"**Status:** {queue['status']} | **ETA:** {queue['timeleft']}\n" \
                                                f"**Task ID:** `{queue['nzo_id']}`\n━━━━━━━━━━━━━━━━━━━━\n"
                else:
                    status_embed.description += f'**🗂 FileName:** `{file_name}`\n' \
                        f"**Status:** *Queued*\n" \
                        f"**Task ID:** `{queue['nzo_id']}`\n━━━━━━━━━━━━━━━━━━━━\n"
                # Show only first 5 items in queue
                if index == 4 and len(downloading_queue_list) > 5:
                    status_embed.description += f"**+ {max(len(downloading_queue_list)-5, 0)} Ongoing Tasks...**\n\n"
                    break

        if postprocessing_queue_list:
            if status_embed.description not in ['', None]:
                status_embed.description += '━━━━━━━━━━━━━━━━━━━━\n'
            status_embed.description += "**Post Processing**\n\n"
            for index, history in enumerate(postprocessing_queue_list):
                file_name = history["name"]
                if re.search(r"(http|https)", file_name):
                    file_name = "N/A"

                status_embed.description += f"**🗂 FileName: ** `{file_name}`\n"
                action = history.get("action_line")
                if isinstance(action, list):
                    status_embed.description += f"**Status: ** {history['status']}\n"
                    status_embed.description += f"**Action: ** ```\n{action[0]}\n```\n\n"

                elif action and "Running script:" in action:
                    status_embed.description += f"**Status: ** *Uploading to GDrive*\n"
                    action = action.replace("Running script:", "")
                    # Uploading to drive: 4.270 GiB / 11.337 GiB, 38%, 20.453 MiB/s, ETA 5m53s
                    speed_pattern = r"(\d+\.\d+ [KMG]?i?B\/s)"
                    eta_pattern = r"ETA ((\d+h)?(\d+m)?(\d+s)?)"

                    speed_match = re.search(speed_pattern, action)
                    eta_match = re.search(eta_pattern, action)
                    if speed_match and eta_match:
                        speed = speed_match.group(0)
                        eta = eta_match.group(1)
                        status_embed.description += f"**Speed: **{speed} **ETA: **{eta}\n\n"
                    elif any(substring in action for substring in ["Uploading to drive", "File has been successfully", "File deleted:", "Directory deleted:", ".py"]):
                        status_embed.description += ""
                    else:
                        status_embed.description += f"**Action:** ```\n{action.strip()}\n```\n\n"
                elif action and "Unpacking" in action:
                    status_embed.description += f"**Status: ** *Unpacking files*\n\n"
                else:
                    status_embed.description += f"**Status: ** *{history['status']}*\n\n"

                if index == 4 and len(postprocessing_queue_list) > 4:
                    status_embed.description += f"\n**+ Extra Queued Task...**\n\n"
                    break

        if status_embed.description not in ['', None]:
            status_embed.set_footer(text=self.footer_message())

        return '', status_embed

    # async def get_file_names(self, task_ids):
    #     logger.info(f"Recieved get_file_names({task_ids})")
    #     file_names = []
    #     for task_id in task_ids:
    #         task = await self.get_task(task_id)
    #         while not task:
    #             try:
    #                 task = await asyncio.wait_for(self.get_task(task_id), timeout=20)
    #             except asyncio.TimeoutError:
    #                 logger.info(
    #                     f"Timeout 1 done, we could not find task with specified ID.")
    #                 break
    #         logger.info(f"recieved task: {task}")
    #         if task:
    #             file_name = task[0]['filename']
    #             while re.search(r"(http|https)", file_name):
    #                 try:
    #                     task = await asyncio.wait_for(self.get_task(task_id), timeout=20)
    #                     if task:
    #                         file_name = task[0]["filename"]
    #                 except asyncio.TimeoutError:
    #                     logger.info(f"Timeout 2 done")
    #                     break
    #             if not re.search(r"(http|https)", file_name):
    #                 file_names.append(file_name)
    #     return file_names
    async def get_file_names(self, task_ids):
        logger.info(f"Received get_file_names({task_ids})")
        file_names = []

        for task_id in task_ids:
            try:
                task = None
                while not task:
                    task = await asyncio.wait_for(self.get_task(task_id), timeout=20)
            except asyncio.TimeoutError:
                logger.info(f"Timeout occurred. Could not find task with specified ID: {task_id}")
                continue

            while task:
                file_name = task[0]['filename']
                while re.search(r"(http|https)", file_name):
                    try:
                        task = await asyncio.wait_for(self.get_task(task_id), timeout=20)
                        if task:
                            file_name = task[0]["filename"]
                    except asyncio.TimeoutError:
                        logger.info(f"Timeout occurred while retrieving file name.")
                        break

                if not re.search(r"(http|https)", file_name):
                    file_names.append(file_name)

                break  # Exit the while loop after processing the task

        return file_names


    async def check_task(self, task_id):
        response = await self.client.get(
            self.SABNZBD_API, params={"mode": "queue", "nzo_ids": task_id})

        response = response.json()
        return bool(response["queue"]["slots"])

    async def get_task(self, task_id):
        response = await self.client.get(
            self.SABNZBD_API, params={"mode": "queue", "nzo_ids": task_id})

        response = response.json()
        return response["queue"]["slots"]

    async def resume_task(self, task_id):
        isValidTaskID = await self.check_task(task_id)
        if not isValidTaskID:
            return False

        response = await self.client.get(
            self.SABNZBD_API,
            params={"mode": "queue", "name": "resume", "value": task_id},
        )
        return response.json()

    async def resumeall_task(self):
        response = await self.client.get(self.SABNZBD_API, params={"mode": "resume"})
        response = response.json()
        return response["status"]

    async def pause_task(self, task_id):
        isValidTaskID = await self.check_task(task_id)
        if not isValidTaskID:
            return False

        response = await self.client.get(
            self.SABNZBD_API,
            params={"mode": "queue", "name": "pause", "value": task_id},
        )
        return response.json()

    async def pauseall_task(self):
        response = await self.client.get(self.SABNZBD_API, params={"mode": "pause"})
        response = response.json()
        return response["status"]

    async def delete_task(self, task_id):
        isValidTaskID = await self.check_task(task_id)
        if not isValidTaskID:
            return False

        response = await self.client.get(
            self.SABNZBD_API,
            params={"mode": "queue", "name": "delete", "value": task_id},
        )
        return response.json()

    async def deleteall_task(self):
        response = await self.client.get(
            self.SABNZBD_API, params={"mode": "queue", "name": "delete", "value": "all"})

        response = response.json()
        return response["status"]

    async def add_nzbfile(self, path_name, category: str = None, password: str = None):
        try:
            async with aiofiles.open(path_name, "rb") as file:
                nzb_content = await file.read()
        except:
            return False

        payload = {"nzbfile": (path_name.split("/")[-1], nzb_content)}
        params = {"mode": "addfile"}
        if category:
            params["cat"] = category
        if password:
            params["password"] = password

        response = await self.client.post(
            self.SABNZBD_API, params=params, files=payload)

        return response.json()

    async def add_nzburl(self, nzburl, category: str = None):
        params = {"mode": "addurl", "name": nzburl}
        if category:
            params["cat"] = category
        response = await self.client.post(self.SABNZBD_API, params=params)
        return response.json()

    async def clear_progresstask(self, status_message, msg_id, **kwargs):
        """remove job, delete message and clear dictionary of progress bar."""

        scheduler.remove_job(f"{str(msg_id)}")
        # try:
        # await status_message.delete()
        excess = ''
        if kwargs.get('jump_url'):
            excess += f':\n[Latest Message]({kwargs.get("jump_url")})'

        em = discord.Embed(title='📊 Status', color=discord.Color.green())
        em.description = f'No Current Tasks or see the latest status message{excess}'
        await status_message.edit(content='', embed=em)
        # except Exception as e:
        #     pass  # passing errors like status message deleted.

        if kwargs.get('pop_dict') == False:
            return

        downloading_status_msgids.pop(msg_id)

    async def show_downloading_status(self, bot: commands.Bot, channel_id, message: discord.Message):

        # Get the status page
        status_page, status_embed = await self.downloading_status_page()
        # print(status_embed.description)
        # print()
        # print(status_page)

        # if not status_page:
        #     # chan = await bot.fetch_channel(channel_id)
        #     # await chan.fetch_message(message)
        #     return await message.reply(content="No ongoing task currently.",mention_author=False)

        if status_embed.description in ['', None]:
            # chan = await bot.fetch_channel(channel_id)
            # await chan.fetch_message(message)
            return await message.reply(content="No ongoing task currently.", mention_author=False)

        # Send the status message and start the job to update the downloading status message after x interval.
        status_message = await message.reply(embed=status_embed, mention_author=False)

        # Remove previous status message and scheduled job for that chat_id
        # print(message.id)
        # print(downloading_status_msgids)
        if message.id in downloading_status_msgids:
            # print('yess')
            status_message_id = downloading_status_msgids[message.id]
            chan = await bot.fetch_channel(channel_id)
            status_message_old = await chan.fetch_message(status_message_id)
            await self.clear_progresstask(status_message_old, message.id)
        else:
            for message.id in downloading_status_msgids:
                status_message_id = downloading_status_msgids[message.id]
                chan = await bot.fetch_channel(channel_id)
                status_message_old = await chan.fetch_message(status_message_id)
                await self.clear_progresstask(status_message_old, message.id, pop_dict=False, jump_url=status_message.jump_url)

            downloading_status_msgids.clear()

        downloading_status_msgids[message.id] = status_message.id

        async def edit_status_message():
            """Edit the status message  after x seconds."""

            status_page, status_embed = await self.downloading_status_page()
            # if not status_page:
            #     return await self.clear_progresstask(status_message, message.id)

            if status_embed.description in ['', None]:
                return await self.clear_progresstask(status_message, message.id)

            try:
                await status_message.edit(content=status_page, embed=status_embed)
            except Exception as e:
                logger.warn('edit_status_msg_exception\n'+str(e))
                await self.clear_progresstask(status_message, message.id)

        scheduler.add_job(
            edit_status_message,
            "interval",
            seconds=10,
            misfire_grace_time=15,
            max_instances=2,
            id=f"{str(message.id)}")


def cog_check():
    def predicate(ctx: commands.Context):
        if len(AUTHORIZED_CHANNELS_LIST) == 0:
            return True
        if ctx.message.channel.id in AUTHORIZED_CHANNELS_LIST:
            return True
        elif ctx.author.id == SUDO_USERIDS[0]:
            return True
        else:
            return False
    return commands.check(predicate)


class Usenet(commands.Cog):
    """Usenet commands"""

    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.usenetbot = UsenetHelper()

    async def cog_before_invoke(self, ctx):
        """
        Triggers typing indicator on Discord before every command.
        """
        await ctx.channel.typing()
        return

    @commands.command(name='status', aliases=['dstatus'])
    @cog_check()
    async def status_command(self, ctx: commands.Context):
        logger.info(f'{ctx.author.name} ({ctx.author.id}) ran status command')
        reference = ctx.message.reference
        message = ctx.message
        if reference and reference.message_id:
            chan_id = await self.bot.fetch_channel(reference.channel_id)
            message = await chan_id.fetch_message(reference.message_id)

        return await self.usenetbot.show_downloading_status(self.bot, ctx.channel.id, message)

    @commands.command()
    @cog_check()
    @sudo_check()
    async def resumeall(self, ctx):
        logger.info(
            f'{ctx.author.name} ({ctx.author.id}) ran resumeall command')
        res = await self.usenetbot.resumeall_task()
        if res:
            await ctx.send('Resumed all tasks successfully')
        else:
            await ctx.send('Unable to do what you asked. Please check logs')

    @commands.command()
    @cog_check()
    @sudo_check()
    async def pauseall(self, ctx):
        logger.info(
            f'{ctx.author.name} ({ctx.author.id}) ran pauseall command')
        res = await self.usenetbot.pauseall_task()
        if res:
            await ctx.send('Paused all tasks successfully')
        else:
            await ctx.send('Unable to do what you asked. Please check logs')

    @commands.command(aliases=['deleteall'])
    @cog_check()
    @sudo_check()
    async def cancelall(self, ctx):
        logger.info(
            f'{ctx.author.name} ({ctx.author.id}) ran cancelall command')
        res = await self.usenetbot.deleteall_task()
        if res:
            await ctx.send('Cancelled all tasks successfully')
        else:
            await ctx.send('Unable to do what you asked. Please check logs')

    @commands.command()
    @cog_check()
    async def pause(self, ctx: commands.Context, task_id: str = None):
        if not task_id:
            return await ctx.send(f'Please send the task id of the task you want to pause along with the command. `{ctx.prefix}pause SABnzbd_nzo_6w6458gv` . If the `_` convert the id to italics, no need to worry about it.')
        task_id = task_id.replace('\\', '')
        if not ctx.author.id in SUDO_USERIDS:
            if ctx.author.id not in sabnzbd_userid_log:
                return await ctx.reply('No task found which you initiated....', mention_author=False)

            if task_id not in sabnzbd_userid_log[ctx.author.id]:
                return await ctx.reply('No task found which you initiated, with that task id.', mention_author=False)

        res = await self.usenetbot.pause_task(task_id=task_id)
        logger.info(
            f'{ctx.author.name} ({ctx.author.id}) ran pause command for {task_id} which resulted in {"success" if res else "failure"}')
        if res:
            await ctx.reply(f'Successfully paused task with task id: `{task_id}`', mention_author=False)
        else:
            await ctx.reply(f'No task found with task id: `{task_id}`', mention_author=False)

    @commands.command()
    @cog_check()
    async def resume(self, ctx: commands.Context, task_id: str = None):
        if not task_id:
            return await ctx.send(f'Please send the task id of the task you want to resume along with the command. `{ctx.prefix}resume SABnzbd_nzo_6w6458gv` . If the `_` convert the id to italics, no need to worry about it.')
        task_id = task_id.replace('\\', '')
        if not ctx.author.id in SUDO_USERIDS:
            if ctx.author.id not in sabnzbd_userid_log:
                return await ctx.reply('No task found which you initiated....', mention_author=False)

            if task_id not in sabnzbd_userid_log[ctx.author.id]:
                return await ctx.reply('No task found which you initiated, with that task id.', mention_author=False)

        res = await self.usenetbot.resume_task(task_id=task_id)
        logger.info(
            f'{ctx.author.name} ({ctx.author.id}) ran resume command for {task_id} which resulted in {"success" if res else "failure"}')
        if res:
            await ctx.reply(f'Successfully resumed task with task id: `{task_id}`', mention_author=False)
        else:
            await ctx.reply(f'No task found with task id: `{task_id}`', mention_author=False)

    @commands.command(aliases=['cancel'])
    @cog_check()
    async def delete(self, ctx: commands.Context, task_id: str = None):
        if not task_id:
            return await ctx.send(f'Please send the task id of the task you want to cancel or delete along with the command. `{ctx.prefix}cancel SABnzbd_nzo_6w6458gv` . If the `_` convert the id to italics, no need to worry about it.')
        task_id = task_id.replace('\\', '')
        if not ctx.author.id in SUDO_USERIDS:
            if ctx.author.id not in sabnzbd_userid_log:
                return await ctx.reply('No task found which you initiated....', mention_author=False)

            if task_id not in sabnzbd_userid_log[ctx.author.id]:
                return await ctx.reply('No task found which you initiated, with that task id.', mention_author=False)

        res = await self.usenetbot.delete_task(task_id=task_id)
        logger.info(
            f'{ctx.author.name} ({ctx.author.id}) ran delete command for {task_id} which resulted in {"success" if res else "failure"}')
        if res:
            await ctx.reply(f'Successfully cancelled task with task id: `{task_id}`', mention_author=False)
        else:
            await ctx.reply(f'No task found with task id: `{task_id}`', mention_author=False)

    @commands.command()
    @cog_check()
    async def nzbmirror(self, ctx: commands.Context, *, params: str = None):
        attachments = ctx.message.attachments
        if len(attachments) == 0:
            return await ctx.send('Please send one or multiple .nzb files along with this command.')

        if params:
            params = params.strip().split()

        is_pack = False
        password = None
        if params:
            if params[0] == "-p":
                is_pack = True
            password_param = [
                param for param in params if param.startswith("--pass=")]
            if password_param:
                password = password_param[0].split("=")[1]
                logger.info(
                    f'Password was given for mirror command: {password}')

        any_one_added = False
        files_added = []
        for nzb_file in attachments:
            if not nzb_file.filename.endswith('.nzb'):
                await ctx.send(f'`{nzb_file.filename}` is not a .nzb file')
                continue
            reply_msg = await ctx.reply('Adding nzb file(s) please wait....', mention_author=False)
            await nzb_file.save(fp=f'nzbfiles/{nzb_file.filename}')

            res = await self.usenetbot.add_nzbfile(f'nzbfiles/{nzb_file.filename}', sabnzbd_pack_category if is_pack else None, password)
            logger.info(
                f'{ctx.author.name} ({ctx.author.id}) added nzb file ({nzb_file.filename}) which resulted in {"success" if res["status"] else "failure"}')
            if res['status']:
                any_one_added = True
                sabnzbd_userid_log.setdefault(
                    ctx.author.id, []).append(res["nzo_ids"][0])
                files_added.append(nzb_file.filename)
            else:
                return await reply_msg.edit(content=f"Something went wrong while processing your NZB file `{nzb_file.filename}`. Ignoring other attachments.")

        formatted_file_names = "\n".join(["`" + s + "`" for s in files_added])
        if any_one_added:
            return await reply_msg.edit(content=f"**Following files were added to queue by uploading:\n{formatted_file_names}\nAdded by: <@{ctx.message.author.id}>\n(To view status send `{prefix}status`.)**")

    @commands.command(aliases=['nzbgrab', 'nzbadd', 'grab'])
    @cog_check()
    async def grabid(self, ctx: commands.Context, *, nzbids: str = None):
        if not nzbids:
            return await ctx.send(f'Please also send a nzb id to grab ... `{ctx.prefix}grab 5501963429970569893`\nYou can also send multiple ids in one go. Just partition them with a space.')
        nzbids = nzbids.strip()
        nzbhydra_idlist = nzbids.split()
        if not nzbhydra_idlist:
            return await ctx.send("No IDs were sent. Please provide a proper ID.")
        replymsg = await ctx.reply("Adding your requested ID(s). Please Wait...", mention_author=False)
        success_taskids = []
        is_pack = False
        if nzbhydra_idlist[0] == "-p":
            is_pack = True
            nzbhydra_idlist.remove("-p")
        for id in nzbhydra_idlist:
            # Make sure that we are getting a number and not letters..
            if id.startswith("-"):
                if not id[1:].isnumeric():
                    await ctx.send(f"`{id}` is invalid. Please provide a proper ID. Ignoring other inputs.")
                    break
            elif not id.isnumeric():
                await ctx.send(f"`{id}` is invalid. Please provide a proper ID. Ignoring other inputs.")
                break

            nzburl = NZBHYDRA_URL_ENDPOINT.replace("replace_id", id)
            try:
                # response = requests.get(nzburl)
                # if "Content-Disposition" in response.headers:
                    result = await self.usenetbot.add_nzburl(nzburl, sabnzbd_pack_category if is_pack else None)
                    logger.info(
                        f'[GET] {ctx.author.name} ({ctx.author.id}) added nzb id ({id}) which resulted in {"success" if result["status"] else "failure"} | {result} | 2')
                    if result["status"]:
                        success_taskids.append(result["nzo_ids"][0])
                    else:
                        logger.info(
                        f'{ctx.author.name} ({ctx.author.id}) added nzb id ({id}) which resulted in failure.')
                        await ctx.send(f'Unable to add {id}, try again later.')
                # elif 'Retry-After' in response.headers:
                #     logger.info(
                #         f'{ctx.author.name} ({ctx.author.id}) added nzb id ({id}) which resulted in failure due getting Retry-After.')
                #     await ctx.send(f'Unable to add {id} , got a retry after message. Retry after {str(response.headers.get("Retry-After"))} seconds <t:{round(datetime.datetime.now().timestamp()+int(response.headers.get("Retry-After")))}:R>')
                # else:
                #     if "outdated search result ID" in str(response.content).lower():
                #         await ctx.send(f"`{id}` is invalid. Please provide a proper ID. Ignoring other inputs.")
                #         break
                #     else:
                #         logger.info(
                #             f'Some error has occured. \n Details: ```\n{remove_private_stuff(str(nzburl))}\n\n{remove_private_stuff(str(response.content))}\n\n{remove_private_stuff(str(response.headers))}```')
                #         await ctx.send(content=f"An error occured while adding {id}. \nReport sent to sudo user.")
            except requests.RequestException as e:
                logger.info(f"An error occurred during the request: {str(e)}")
        if success_taskids:
            sabnzbd_userid_log.setdefault(
                ctx.author.id, []).extend(success_taskids)
            await replymsg.edit(content=f"Added successfully!\nWaiting to get file names...")
            
            # This is to make sure the nzb's have been added to sabnzbd
            # TODO: Find a better way and more dynamic way to handle it.
            await asyncio.sleep(5)
            try:
                file_names = await self.usenetbot.get_file_names(success_taskids)
                if file_names:
                    logger.info(f"Retrieved file name(s): {file_names}")
                    formatted_file_names = "\n".join(
                        ["`" + s + "`" for s in file_names])
                    return await replymsg.edit(content=f"**Following files were added to queue:\n{formatted_file_names}\nAdded by: <@{ctx.message.author.id}>\n(To view status send `{prefix}status`.)**")
                else:
                    return await replymsg.edit(content=f"**No files were added to the queue.\n<@{ctx.message.author.id}>\n(To view status send `{prefix}status`.)**")
            except Exception as e:
                logger.exception('An error occurred while retrieving file names')
                return await replymsg.edit(content="Error retrieving file names\nAdded by: <@{ctx.message.author.id}>")
    # Handle the error accordingly (e.g., log the error, send an error message, etc.)
    # You can choose to return an error message or take other appropriate actions.
      

        return await replymsg.edit(content="No task has been added.")


async def setup(bot):
    await bot.add_cog(Usenet(bot))
    print("Usenet cog is loaded")

discord.Color.green()
