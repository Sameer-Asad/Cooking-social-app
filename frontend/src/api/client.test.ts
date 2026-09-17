import { describe, expect, it } from "vitest";
import { mediaUrl } from "./client";

describe("mediaUrl", () => {
  it("passes through an already-prefixed /media/ path unchanged", () => {
    expect(mediaUrl("/media/audio/abc123.mp3")).toBe("/media/audio/abc123.mp3");
  });

  it("adds the /media/ prefix to a bare relative path (a post's media_path)", () => {
    expect(mediaUrl("images/xyz.jpg")).toBe("/media/images/xyz.jpg");
  });

  it("strips a leading slash before re-adding the /media/ prefix, avoiding a double slash", () => {
    expect(mediaUrl("/images/xyz.jpg")).toBe("/media/images/xyz.jpg");
  });
});
