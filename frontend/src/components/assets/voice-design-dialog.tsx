// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Sparkles, WandSparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export type VoiceDesignInput = {
  description: string;
  previewText: string;
};

export function VoiceDesignDialog({
  open,
  onOpenChange,
  title,
  initialDescription,
  initialPreviewText,
  pending,
  optimizing,
  onOptimize,
  onGenerate,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  initialDescription: string;
  initialPreviewText: string;
  pending: boolean;
  optimizing: boolean;
  onOptimize: (input: VoiceDesignInput) => Promise<string | null>;
  onGenerate: (input: VoiceDesignInput) => Promise<boolean>;
}) {
  const { t } = useTranslation();
  const [description, setDescription] = useState(initialDescription);
  const [previewText, setPreviewText] = useState(initialPreviewText);

  useEffect(() => {
    if (!open) return;
    setDescription(initialDescription);
    setPreviewText(initialPreviewText);
  }, [open, initialDescription, initialPreviewText]);

  const submit = async () => {
    if (!description.trim() || !previewText.trim()) return;
    if (await onGenerate({ description: description.trim(), previewText: previewText.trim() })) {
      onOpenChange(false);
    }
  };

  const optimize = async () => {
    if (!description.trim()) return;
    const optimized = await onOptimize({
      description: description.trim(),
      previewText: previewText.trim(),
    });
    if (optimized) setDescription(optimized);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent className="gap-4 rounded-2xl border border-white/[0.08] bg-zinc-950/30 p-5 shadow-2xl shadow-black/40 backdrop-blur-2xl sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-lg font-medium tracking-tight text-foreground">
            {title}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <div className="flex min-h-7 items-center justify-between gap-3">
              <Label htmlFor="voice-design-description" className="text-xs text-muted-foreground">
                {t("voiceDesign.description")}
              </Label>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={pending || optimizing || !description.trim()}
                onClick={() => void optimize()}
                className="h-7 gap-1.5 px-2 text-xs text-muted-foreground hover:text-foreground"
              >
                {optimizing ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
                {optimizing ? t("voiceDesign.optimizing") : t("voiceDesign.optimize")}
              </Button>
            </div>
            <Textarea
              id="voice-design-description"
              value={description}
              maxLength={1000}
              rows={4}
              onChange={(event) => setDescription(event.target.value)}
              placeholder={t("voiceDesign.descriptionPlaceholder")}
              className="resize-none rounded-[8px] border-white/[0.10] bg-white/[0.04] text-sm leading-6 shadow-none focus:border-white/[0.18]"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="voice-design-preview" className="text-xs text-muted-foreground">
              {t("voiceDesign.previewText")}
            </Label>
            <Textarea
              id="voice-design-preview"
              value={previewText}
              maxLength={500}
              rows={3}
              onChange={(event) => setPreviewText(event.target.value)}
              placeholder={t("voiceDesign.previewPlaceholder")}
              className="resize-none rounded-[8px] border-white/[0.10] bg-white/[0.04] text-sm leading-6 shadow-none focus:border-white/[0.18]"
            />
          </div>
        </div>
        <DialogFooter className="mt-2 flex flex-col gap-2 sm:flex-row sm:justify-end sm:gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={pending || optimizing}
            onClick={() => onOpenChange(false)}
          >
            {t("common.cancel")}
          </Button>
          <Button
            type="button"
            disabled={pending || optimizing || !description.trim() || !previewText.trim()}
            onClick={() => void submit()}
          >
            {pending ? <Loader2 className="size-4 animate-spin" /> : <WandSparkles className="size-4" />}
            {pending ? t("voiceDesign.generating") : t("voiceDesign.generate")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
