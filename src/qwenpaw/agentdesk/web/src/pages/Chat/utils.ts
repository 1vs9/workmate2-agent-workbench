/**
 * Rewrite a media/file reference to a browser-displayable URL.
 * MVP: files are served as-is by the backend, so this is identity. Kept as a
 * seam so file/image URL rewriting can be added without touching call sites.
 */
export function toDisplayUrl(url: string): string {
  return url;
}

interface ContentItem {
  type: string;
  text?: string;
  [key: string]: unknown;
}

/** Apply toDisplayUrl to media URLs inside a content item. */
export function normalizeContentUrls(item: ContentItem): ContentItem {
  if (item.type === "image" && item.image_url) {
    return { ...item, image_url: toDisplayUrl(item.image_url as string) };
  }
  if (item.type === "audio" && item.data) {
    return { ...item, data: toDisplayUrl(item.data as string) };
  }
  if (item.type === "video" && item.video_url) {
    return { ...item, video_url: toDisplayUrl(item.video_url as string) };
  }
  if (item.type === "file" && (item.file_url || item.file_id)) {
    return {
      ...item,
      file_url: toDisplayUrl(
        (item.file_url as string) || (item.file_id as string),
      ),
    };
  }
  return item;
}

/** Join the text parts of a message's content array into a single string. */
export function extractUserMessageText(msg: {
  content?: unknown;
}): string {
  const content = msg.content;
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return (content as ContentItem[])
    .filter((c) => c.type === "text")
    .map((c) => c.text || "")
    .filter(Boolean)
    .join("\n");
}
