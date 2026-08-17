// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { VoiceDesignDialog } from "@/components/assets/voice-design-dialog";

const i18n = i18next.createInstance();

beforeAll(async () => {
  await i18n.use(initReactI18next).init({
    lng: "zh",
    resources: {
      zh: {
        translation: {
          common: { cancel: "取消" },
          voiceDesign: {
            description: "声线描述",
            previewText: "试听文本",
            optimize: "AI 优化提示词",
            optimizing: "优化中",
            generate: "生成并使用",
            generating: "生成中",
          },
        },
      },
    },
  });
});

describe("VoiceDesignDialog", () => {
  it("replaces the editable description with the AI-optimized result", async () => {
    const user = userEvent.setup();
    const optimize = vi.fn().mockResolvedValue("更清晰、克制且富有层次的青年男声");

    render(
      <I18nextProvider i18n={i18n}>
        <VoiceDesignDialog
          open
          onOpenChange={vi.fn()}
          title="生成声线"
          initialDescription="年轻男声"
          initialPreviewText="今晚必须离开这里。"
          pending={false}
          optimizing={false}
          onOptimize={optimize}
          onGenerate={vi.fn()}
        />
      </I18nextProvider>,
    );

    await user.click(screen.getByRole("button", { name: "AI 优化提示词" }));

    expect(optimize).toHaveBeenCalledWith({
      description: "年轻男声",
      previewText: "今晚必须离开这里。",
    });
    expect(await screen.findByDisplayValue("更清晰、克制且富有层次的青年男声")).toBeInTheDocument();
  });
});
