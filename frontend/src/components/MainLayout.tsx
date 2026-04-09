"use client";

import { useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Layout, Menu, Typography } from "antd";
import {
  MessageOutlined,
  FileAddOutlined,
  EditOutlined,
  UnorderedListOutlined,
  DashboardOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import type { MenuProps } from "antd";

const { Sider, Content, Header } = Layout;
const { Title } = Typography;

const menuItems: MenuProps["items"] = [
  {
    key: "/",
    icon: <DashboardOutlined />,
    label: "首页",
  },
  {
    key: "/interview",
    icon: <TeamOutlined />,
    label: "模拟面试",
  },
  {
    key: "/chat",
    icon: <MessageOutlined />,
    label: "AI 对话",
  },
  {
    key: "/extract",
    icon: <FileAddOutlined />,
    label: "录入面经",
  },
  {
    key: "/practice",
    icon: <EditOutlined />,
    label: "练习答题",
  },
  {
    key: "/questions",
    icon: <UnorderedListOutlined />,
    label: "题目管理",
  },
  {
    key: "/dashboard",
    icon: <DashboardOutlined />,
    label: "数据仪表盘",
  },
];

interface MainLayoutProps {
  children: React.ReactNode;
}

export default function MainLayout({ children }: MainLayoutProps) {
  const [collapsed, setCollapsed] = useState(false);
  const router = useRouter();
  const pathname = usePathname();

  const handleMenuClick: MenuProps["onClick"] = ({ key }) => {
    router.push(key);
  };

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="light"
        style={{
          borderRight: "1px solid #f0f0f0",
        }}
      >
        <div
          style={{
            height: 64,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            borderBottom: "1px solid #f0f0f0",
            cursor: "pointer",
          }}
          onClick={() => router.push("/")}
        >
          <Title level={4} style={{ margin: 0, color: "#1890ff" }}>
            {collapsed ? "📚" : "Offer-Catcher"}
          </Title>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[pathname]}
          items={menuItems}
          onClick={handleMenuClick}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            padding: "0 24px",
            background: "#fff",
            borderBottom: "1px solid #f0f0f0",
          }}
        >
          <Title level={4} style={{ margin: 0, lineHeight: "64px" }}>
            面试准备智能助手
          </Title>
        </Header>
        <Content
          style={{
            margin: 24,
            padding: 24,
            background: "#fff",
            borderRadius: 8,
            minHeight: 280,
            overflow: "auto",
          }}
        >
          {children}
        </Content>
      </Layout>
    </Layout>
  );
}