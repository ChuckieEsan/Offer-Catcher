"use client";

import { marked } from "marked";
import { memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * 将 Markdown 解析成独立的块
 * 使用 marked.lexer 识别段落、代码块、列表等元素
 */
function parseMarkdownIntoBlocks(markdown: string): string[] {
  try {
    const tokens = marked.lexer(markdown);
    return tokens.map((token) => token.raw);
  } catch {
    // 如果解析失败，返回原始内容
    return [markdown];
  }
}

/**
 * 单个 Markdown 块组件
 * 使用 memo 避免未变化的内容重新渲染
 */
const MemoizedMarkdownBlock = memo(
  ({ content }: { content: string }) => {
    return (
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {content}
      </ReactMarkdown>
    );
  },
  (prevProps, nextProps) => {
    // 内容相同则不重新渲染
    return prevProps.content === nextProps.content;
  }
);

MemoizedMarkdownBlock.displayName = "MemoizedMarkdownBlock";

interface MemoizedMarkdownProps {
  content: string;
  id: string;
  className?: string;
}

/**
 * Memoized Markdown 组件
 *
 * 将 Markdown 内容分割成独立的块，每个块单独缓存。
 * 当流式输出新内容时，只有新增或变化的块会重新渲染，
 * 已有的块保持不变，从而避免整个内容重新解析。
 *
 * @param content - Markdown 内容
 * @param id - 唯一标识符，用于生成稳定的 key
 * @param className - 可选的 CSS 类名
 */
export const MemoizedMarkdown = memo(
  ({ content, id, className }: MemoizedMarkdownProps) => {
    const blocks = useMemo(() => parseMarkdownIntoBlocks(content), [content]);

    return (
      <div className={className}>
        {blocks.map((block, index) => (
          <MemoizedMarkdownBlock
            content={block}
            key={`${id}-block-${index}`}
          />
        ))}
      </div>
    );
  }
);

MemoizedMarkdown.displayName = "MemoizedMarkdown";

/**
 * 流式 Markdown 组件
 *
 * 用于流式输出场景，显示纯文本 + 光标动画，
 * 完成后切换到 Markdown 渲染。
 */
interface StreamingMarkdownProps {
  content: string;
  isComplete: boolean;
  id: string;
}

export function StreamingMarkdown({ content, isComplete, id }: StreamingMarkdownProps) {
  if (isComplete || !content) {
    return (
      <MemoizedMarkdown content={content} id={id} className="markdown-body" />
    );
  }

  // 流式输出时显示纯文本 + 光标
  return (
    <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
      {content}
      <span className="typing-cursor">▊</span>
    </div>
  );
}