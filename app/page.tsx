import type { Metadata } from "next";
import AdminApp from "./AdminApp.tsx";

export const metadata: Metadata = {
  title: "简地内容中台",
  description: "城市深度游内容管理与发布后台",
};

export default function Home() {
  return <AdminApp />;
}
