import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResourceDetailPage } from "./ResourceDetailPage";

vi.mock("./api", () => ({ getResource: vi.fn(async () => ({ id: "video", title: "用户上传的视频" })) }));
vi.mock("./ResourceCard", () => ({ ResourceCard: () => <div>视频播放器</div> }));
vi.mock("../study/api", () => ({ newOpenEventId: () => "open-event", recordOpen: vi.fn(async () => ({})) }));
vi.mock("../companion/useLearningPageContext", () => ({ useLearningPageContext: vi.fn() }));
afterEach(cleanup);

describe("resource player return navigation", () => {
  it.each([
    ["animations", "动画讲解", "/animations"],
    ["activities", "动画与实验", "/activities"],
    ["https://untrusted.example", "资源中心", "/resources"],
  ])("returns safely from %s to the entry catalogue", async (from, label, path) => {
    render(<MemoryRouter initialEntries={[`/resources/video?from=${encodeURIComponent(from)}`]}><Routes>
      <Route path="/resources/video" element={<ResourceDetailPage />} />
      <Route path={path} element={<h1>返回目录</h1>} />
    </Routes></MemoryRouter>);
    await screen.findByRole("heading", { name: "用户上传的视频" });
    fireEvent.click(screen.getByRole("button", { name: `← 返回${label}` }));
    expect(await screen.findByRole("heading", { name: "返回目录" })).toBeTruthy();
  });
});
