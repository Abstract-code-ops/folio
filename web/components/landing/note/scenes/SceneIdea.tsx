import { motion } from "framer-motion";
import { rectPath, strokeVariants } from "./SceneFrame";

const ink = "rgb(var(--scene-ink))";
const soft = "rgb(var(--scene-ink-soft))";
const fill = "rgb(var(--scene-fill))";
const accent = "rgb(var(--accent))";

export function SceneIdea() {
  return (
    <>
      <motion.path d="M14 176H246" stroke={ink} strokeWidth="2" fill="none" variants={strokeVariants} />
      <motion.path d="M14 182H246" stroke={soft} strokeWidth="1" fill="none" variants={strokeVariants} />
      <motion.path d={rectPath(28, 76, 22, 100)} fill={fill} stroke={ink} strokeWidth="1.6" variants={strokeVariants} />
      <motion.path d="M28 92h22M28 160h22" stroke={soft} strokeWidth="1" fill="none" variants={strokeVariants} />
      <motion.path d={rectPath(52, 94, 18, 82)} fill={fill} stroke={ink} strokeWidth="1.6" variants={strokeVariants} />
      <motion.path d={rectPath(80, 46, 34, 130)} fill={fill} stroke={accent} strokeWidth="2" variants={strokeVariants} />
      <motion.path d="M80 66h34M80 158h34" stroke={accent} strokeWidth="1.2" fill="none" variants={strokeVariants} />
      <g transform="rotate(-3 176 120)">
        <motion.path d={rectPath(128, 84, 108, 76)} fill="rgb(var(--bg-surface))" stroke={ink} strokeWidth="1.2" variants={strokeVariants} />
        <motion.path d="M140 104h50" stroke={accent} strokeWidth="2" fill="none" variants={strokeVariants} />
        <motion.path d="M140 120h82M140 132h76M140 144h54" stroke={soft} strokeWidth="1.2" fill="none" variants={strokeVariants} />
      </g>
    </>
  );
}
