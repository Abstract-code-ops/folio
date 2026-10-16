import type { ComponentType } from "react";
import { SceneProblem } from "./SceneProblem";
import { SceneBook } from "./SceneBook";
import { SceneIdea } from "./SceneIdea";
import { SceneHope } from "./SceneHope";

export const sceneRegistry: Record<string, ComponentType> = {
  problem: SceneProblem,
  book: SceneBook,
  idea: SceneIdea,
  hope: SceneHope,
};

// Neutral fallback for unknown beat ids — a single open page.
export function SceneFallback() {
  return (
    <g>
      <path
        d="M130 160C108 148 80 146 54 152V74C80 68 108 70 130 82Z"
        fill="rgb(var(--scene-fill))"
        stroke="rgb(var(--scene-ink))"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
      <path d="M130 82V160" stroke="rgb(var(--scene-ink))" strokeWidth="1.6" fill="none" />
    </g>
  );
}
