import { useState } from "react";
import {
  ChevronsUp,
  ChevronUp,
  ChevronDown,
  Ban,
  Search,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useCreateReaction, useAnalyzeTweet } from "@/hooks/use-reactions";
import { toast } from "@/components/ui/toaster";
import { ReactionModal } from "./ReactionModal";
import type { AnalyzeResult } from "@/api/types";

interface TweetActionsProps {
  tweetId: string;
  authorHandle: string;
  onAnalyze?: (result: AnalyzeResult) => void;
}

export function TweetActions({ tweetId, authorHandle, onAnalyze }: TweetActionsProps) {
  const [showModal, setShowModal] = useState<string | null>(null);
  const createReaction = useCreateReaction();
  const analyzeMutation = useAnalyzeTweet();

  const react = (type: string, reason?: string, target?: string) => {
    createReaction.mutate(
      { tweet_id: tweetId, reaction_type: type, reason, target },
      {
        onSuccess: (data) => {
          toast(data.message ?? `Reaction ${type} recorded`, "success");
        },
        onError: () => toast("Failed to save reaction", "error"),
      },
    );
  };

  const handleAnalyze = () => {
    analyzeMutation.mutate(tweetId, {
      onSuccess: (result) => {
        if (result.error) {
          toast(result.error, "error");
        } else {
          onAnalyze?.(result);
        }
      },
      onError: () => toast("Analysis failed", "error"),
    });
  };

  return (
    <div className="flex items-center gap-0.5">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-zinc-600 hover:text-green-400"
            onClick={() => setShowModal(">>")}
          >
            <ChevronsUp className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Top tier</TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-zinc-600 hover:text-cyan-400"
            onClick={() => setShowModal(">")}
          >
            <ChevronUp className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Underrated</TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-zinc-600 hover:text-yellow-500"
            onClick={() => setShowModal("<")}
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Overrated</TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-zinc-600 hover:text-red-400"
            onClick={() => react("x_author", undefined, authorHandle)}
            disabled={createReaction.isPending}
          >
            <Ban className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Mute @{authorHandle}</TooltipContent>
      </Tooltip>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 text-zinc-600 hover:text-cyan-400"
            onClick={handleAnalyze}
            disabled={analyzeMutation.isPending}
          >
            {analyzeMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Search className="h-3.5 w-3.5" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent>Deep analyze</TooltipContent>
      </Tooltip>

      {showModal && (
        <ReactionModal
          type={showModal}
          onConfirm={(reason) => {
            react(showModal, reason);
            setShowModal(null);
          }}
          onClose={() => setShowModal(null)}
        />
      )}
    </div>
  );
}
