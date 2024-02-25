
from io import BytesIO
from typing import Tuple
from PIL import Image
from pillow_heif import HeifImagePlugin
from typing import Type

from maubot import Plugin, MessageEvent
from maubot.handlers import command
from mautrix.client import Client as MatrixClient
from mautrix.crypto import attachments
from mautrix.types import EncryptedFile, ImageInfo, MediaMessageEventContent, MessageType
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper

class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("rooms")



async def download_encrypted_media(
        file: EncryptedFile,
        client: MatrixClient) -> bytes:
    """
    Download an encrypted media file
    :param file: The `EncryptedFile` instance, from MediaMessageEventContent.file.
    :param client: The Matrix client. Can be accessed via MessageEvent.client
    :return: The media file as bytes.
    """
    return attachments.decrypt_attachment(
        await client.download_media(file.url),
        file.key.key,
        file.hashes['sha256'],
        file.iv
    )


async def download_unencrypted_media(
        url, 
        client: MatrixClient) -> bytes:
    """
    Download an unencrypted media file
    :param url: The media file mxc url, from MediaMessageEventContent.url.
    :param client: The Matrix client. Can be accessed via MessageEvent.client
    :return: The media file as bytes.
    """
    return await client.download_media(url)


async def send_encrypted_message(
        img_enc,
        room_id,
        info,
        client: MatrixClient) -> None:
    """
    Sends image to an encrypted room
    :param img_enc: The data to upload.
    :param room_id: RoomID.
    :param info: mautrix image info.
    """
    uri = await client.upload_media(
        img_enc[0],
        mime_type="image/jpeg",
        filename="image.jpg"
    )
    content = MediaMessageEventContent(
        msgtype=MessageType.IMAGE,
        body="image.jpg",
        file=EncryptedFile(
            key=img_enc[1].key,
            iv=img_enc[1].iv,
            hashes=img_enc[1].hashes,
            url=uri,
            version=img_enc[1].version
        ), 
        info=ImageInfo(
            mimetype="image/jpeg",
            width=info.width,
            height=info.height
        )
    )
    await client.send_message(room_id, content)


async def send_unencrypted_message(
        img,
        room_id,
        info,
        client: MatrixClient) -> None:
    """
    Sends image to an unencrypted room
    :param img: The data to upload.
    :param room_id: RoomID.
    :param info: mautrix image info.
    """
    uri = await client.upload_media(
        img,
        mime_type="image/jpeg",
        filename="image.jpg"
    )
    content = MediaMessageEventContent(
        msgtype=MessageType.IMAGE,
        body="image.jpg",
        url=uri,
        info=ImageInfo(
            mimetype="image/jpeg",
            width=info.width,
            height=info.height
        )
    )
    await client.send_message(room_id, content)




# BOT
class HateHeifBot(Plugin):

    async def start(self) -> None:
        await super().start()
        self.config.load_and_update()
        self.rooms = self.config['rooms'] if self.config['rooms'] else None


    @command.passive("", msgtypes=(MessageType.IMAGE,MessageType.FILE))
    async def hate_heif_message(
            self,
            evt: MessageEvent,
            match: Tuple[str]) -> None:
        """
        If heif = make it jpg.
        """
        # If there are rooms specified in config, serve only these rooms
        if self.rooms:
            if evt.room_id not in self.rooms:
                self.log.debug(f"Current room {evt.room_id} is not listed in {self.rooms} so I ignore it.")
                return

        # Double check if it is an image message
        if evt.content.msgtype != MessageType.IMAGE and evt.content.msgtype != MessageType.FILE:
            return

        content: MediaMessageEventContent = evt.content
        self.log.debug(f"Received message with an image with MIME: {content.info.mimetype}")

        # We work only on "image/heic" mime at the moment!
        if content.info.mimetype != "image/heic":
            return

        if content.url:  # content.url exists. File is not encrypted.
            data = await download_unencrypted_media(content.url, evt.client)
            is_enc = False
        elif content.file:  # content.file exists. File is encrypted.
            data = await download_encrypted_media(content.file, evt.client)
            is_enc = True
        else:  # shouldn't happen
            self.log.warning("A message with IMAGE type received, but it does not contain a file.")
            return

        # de-heif via pillow
        img_in = Image.open(BytesIO(data))
        self.log.debug(f"Received image parameters: {img_in.format} {img_in.size} {img_in.mode}")
        with BytesIO() as img_out:
            img_in.save(img_out, format="JPEG")
            img = img_out.getvalue()
        img_tst = Image.open(BytesIO(img))
        self.log.debug(f"Created image parameters: {img_tst.format} {img_tst.size} {img_tst.mode}")
        content.info.width=img_tst.size[0]
        content.info.height=img_tst.size[1]

        if is_enc:
            img_enc = attachments.encrypt_attachment(img)
            #self.log.debug(f"{img_enc}")
            await send_encrypted_message(
                    img_enc,
                    evt.room_id,
                    content.info,
                    evt.client
            )
        else:
            await send_unencrypted_message(
                    img,
                    evt.room_id,
                    content.info,
                    evt.client
            )
    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

# the end.
