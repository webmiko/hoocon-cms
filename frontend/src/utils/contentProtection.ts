import type {
  ClipboardEventHandler,
  DragEventHandler,
  ImgHTMLAttributes,
  MouseEventHandler,
  SyntheticEvent,
} from "react";

/**
 * Client-side deterrents against casual photo save / text scrape on product UI.
 *
 * Not DRM: DevTools Network, screenshots, and API JSON still expose paths.
 * Goal: block casual save/copy and hide ``/media/...`` from ``img.src`` via blob URLs.
 */

/** Cancel browser default for copy / cut / context menu / drag. */
export function preventContentTheft(event: SyntheticEvent): void {
  event.preventDefault();
}

type ProtectedMediaImgProps = Pick<
  ImgHTMLAttributes<HTMLImageElement>,
  "draggable" | "onContextMenu" | "onDragStart"
>;

/** Spread onto product `<img>` elements. */
export const protectedMediaImgProps: ProtectedMediaImgProps = {
  draggable: false,
  onContextMenu: preventContentTheft as MouseEventHandler<HTMLImageElement>,
  onDragStart: preventContentTheft as DragEventHandler<HTMLImageElement>,
};

type ProtectedContentHandlers = {
  onCopy: ClipboardEventHandler;
  onCut: ClipboardEventHandler;
};

/** Spread onto product card / PDP content roots (keep RFQ forms outside). */
export const protectedContentHandlers: ProtectedContentHandlers = {
  onCopy: preventContentTheft as ClipboardEventHandler,
  onCut: preventContentTheft as ClipboardEventHandler,
};
