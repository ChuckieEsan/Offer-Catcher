"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Button, Tooltip, message } from "antd";
import { AudioOutlined, AudioMutedOutlined, ReloadOutlined } from "@ant-design/icons";

interface VoiceInputProps {
  onTranscriptChange: (text: string) => void;
  disabled?: boolean;
  language?: string;
}

export default function VoiceInput({
  onTranscriptChange,
  disabled = false,
  language = "zh_cn",
}: VoiceInputProps) {
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [supported, setSupported] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

  // 检查浏览器支持
  useEffect(() => {
    const hasMediaDevices = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    const hasAudioContext = !!(window.AudioContext || (window as any).webkitAudioContext);
    setSupported(hasMediaDevices && hasAudioContext);

    if (!hasMediaDevices || !hasAudioContext) {
      console.log("Browser does not support audio recording");
    }
  }, []);

  // 连接 WebSocket
  const connectWebSocket = useCallback(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
    const wsUrl = apiUrl.replace("http", "ws") + "/ws/speech";

    console.log("Connecting to WebSocket:", wsUrl);

    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log("WebSocket connected");
      // 发送开始消息
      ws.send(JSON.stringify({ type: "start", language }));
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log("WebSocket message:", data);

      if (data.type === "started") {
        console.log("Recognition started");
      } else if (data.type === "result") {
        const text = data.text;
        // 如果是最终结果且文本为空，保持之前的文本
        if (data.is_final) {
          if (text) {
            setTranscript(text);
            onTranscriptChange(text);
          }
          console.log("Recognition ended");
        } else if (text) {
          // 中间结果
          setTranscript(text);
          onTranscriptChange(text);
        }
      } else if (data.type === "error") {
        message.error(data.message);
        stopRecording();
      }
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
      message.error("语音识别连接失败");
      stopRecording();
    };

    ws.onclose = () => {
      console.log("WebSocket closed");
    };

    wsRef.current = ws;
  }, [language, onTranscriptChange]);

  // 开始录音
  const startRecording = useCallback(async () => {
    try {
      // 请求麦克风权限
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });

      mediaStreamRef.current = stream;

      // 创建 AudioContext
      const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
      const audioContext = new AudioContextClass({ sampleRate: 16000 });
      audioContextRef.current = audioContext;

      // 创建音频源
      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;

      // 创建处理器（4096 字节缓冲区）
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      // 连接 WebSocket
      connectWebSocket();

      // 处理音频数据
      processor.onaudioprocess = (event) => {
        if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
          return;
        }

        const inputData = event.inputBuffer.getChannelData(0);

        // 转换为 16bit PCM
        const pcmData = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        // 转换为字节并发送
        const uint8Array = new Uint8Array(pcmData.buffer);
        const base64 = btoa(String.fromCharCode(...uint8Array));

        wsRef.current.send(JSON.stringify({
          type: "audio",
          data: base64,
        }));
      };

      // 连接节点
      source.connect(processor);
      processor.connect(audioContext.destination);

      setListening(true);
      setTranscript("");
      console.log("Recording started");

    } catch (error) {
      console.error("Failed to start recording:", error);
      if ((error as Error).name === "NotAllowedError") {
        message.error("麦克风权限被拒绝，请在浏览器设置中允许访问麦克风");
      } else if ((error as Error).name === "NotFoundError") {
        message.error("未找到麦克风设备");
      } else {
        message.error("启动录音失败");
      }
    }
  }, [connectWebSocket]);

  // 停止录音
  const stopRecording = useCallback(() => {
    // 发送结束消息
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "end" }));
      wsRef.current.close();
    }
    wsRef.current = null;

    // 停止音频处理
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }

    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }

    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    // 停止媒体流
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }

    setListening(false);
    console.log("Recording stopped");
  }, []);

  // 切换录音状态
  const toggleListening = useCallback(() => {
    if (listening) {
      stopRecording();
    } else {
      startRecording();
    }
  }, [listening, startRecording, stopRecording]);

  // 清空转录
  const handleReset = useCallback(() => {
    setTranscript("");
    onTranscriptChange("");
  }, [onTranscriptChange]);

  // 清理
  useEffect(() => {
    return () => {
      if (listening) {
        stopRecording();
      }
    };
  }, [listening, stopRecording]);

  // 如果浏览器不支持，不显示组件
  if (!supported) {
    return null;
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <Tooltip title={listening ? "点击停止录音" : "点击开始录音"}>
        <Button
          type={listening ? "primary" : "default"}
          icon={listening ? <AudioMutedOutlined /> : <AudioOutlined />}
          onClick={toggleListening}
          disabled={disabled}
          danger={listening}
          style={{
            animation: listening ? "pulse 1.5s infinite" : "none",
          }}
        >
          {listening ? "录音中..." : "语音输入"}
        </Button>
      </Tooltip>

      {transcript && (
        <Tooltip title="清空语音输入">
          <Button
            icon={<ReloadOutlined />}
            onClick={handleReset}
            disabled={disabled}
            size="small"
          />
        </Tooltip>
      )}

      {/* 录音动画样式 */}
      <style jsx>{`
        @keyframes pulse {
          0% {
            box-shadow: 0 0 0 0 rgba(255, 77, 79, 0.4);
          }
          70% {
            box-shadow: 0 0 0 10px rgba(255, 77, 79, 0);
          }
          100% {
            box-shadow: 0 0 0 0 rgba(255, 77, 79, 0);
          }
        }
      `}</style>
    </div>
  );
}