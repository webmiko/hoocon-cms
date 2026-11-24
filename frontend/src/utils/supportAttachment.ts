/** Size limits for files sent from the support widget (mirror the API serializer). */

export const ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024;
// nginx ``client_max_body_size`` is 20 MB; stay below it with multipart overhead.
export const MEDIA_ATTACHMENT_MAX_BYTES = 19 * 1024 * 1024;

export function isMediaFile(file: Pick<File, "type">): boolean {
  return file.type.startsWith("video/") || file.type.startsWith("audio/");
}

export function attachmentLimitBytes(file: Pick<File, "type">): number {
  return isMediaFile(file) ? MEDIA_ATTACHMENT_MAX_BYTES : ATTACHMENT_MAX_BYTES;
}

export function attachmentTooBigMessage(file: Pick<File, "type">): string {
  return isMediaFile(file)
    ? "Видео или аудио больше 19 МБ. Пришлите ссылкой на облако или на sales@hoocon.ru."
    : "Файл больше 10 МБ.";
}
