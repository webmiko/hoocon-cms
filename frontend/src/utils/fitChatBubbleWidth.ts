/** Visitor/support chat bubbles: shrink to longest wrapped line, cap at 80% of thread. */
export const CHAT_BUBBLE_WIDTH_CAP_RATIO = 0.8;

function measureLongestLineWidthFallback(element: HTMLElement): number {
  const style = getComputedStyle(element);
  const paddingX =
    parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
  return Math.max(0, element.scrollWidth - paddingX);
}

export function measureLongestLineWidth(element: HTMLElement): number {
  const range = document.createRange();
  if (typeof range.getClientRects !== "function") {
    return measureLongestLineWidthFallback(element);
  }

  let max = 0;
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode() as Text | null;

  while (node) {
    const str = node.textContent ?? "";
    if (!str) {
      node = walker.nextNode() as Text | null;
      continue;
    }

    let lineStart = 0;
    for (let i = 1; i <= str.length; i += 1) {
      range.setStart(node, lineStart);
      range.setEnd(node, i);
      if (range.getClientRects().length > 1) {
        range.setStart(node, lineStart);
        range.setEnd(node, i - 1);
        max = Math.max(max, range.getBoundingClientRect().width);
        lineStart = i - 1;
      }
    }

    range.setStart(node, lineStart);
    range.setEnd(node, str.length);
    max = Math.max(max, range.getBoundingClientRect().width);
    node = walker.nextNode() as Text | null;
  }

  return max;
}

export function fitChatBubbleWidth(
  bubble: HTMLElement,
  messages: HTMLElement,
  capRatio = CHAT_BUBBLE_WIDTH_CAP_RATIO,
): void {
  const messagesWidth = messages.clientWidth;
  if (messagesWidth <= 0) {
    bubble.style.width = "";
    bubble.style.maxWidth = "";
    return;
  }

  const cap = Math.floor(messagesWidth * capRatio);
  bubble.style.maxWidth = `${cap}px`;
  bubble.style.width = `${cap}px`;

  const longest = measureLongestLineWidth(bubble);
  const style = getComputedStyle(bubble);
  const paddingX =
    parseFloat(style.paddingLeft) + parseFloat(style.paddingRight);
  const borderX =
    parseFloat(style.borderLeftWidth) + parseFloat(style.borderRightWidth);
  const target = Math.ceil(longest + paddingX + borderX);

  bubble.style.width = `${Math.min(target, cap)}px`;
}
