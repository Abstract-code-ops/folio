import { motion } from "framer-motion";
import { rectPath, strokeVariants } from "./SceneFrame";

const ink = "rgb(var(--scene-ink))";
const soft = "rgb(var(--scene-ink-soft))";
const fill = "rgb(var(--scene-fill))";
const accent = "rgb(var(--accent))";

export function SceneBook() {
  return (
    <>
      <motion.path d="M20 176H240" stroke={ink} strokeWidth="2" fill="none" variants={strokeVariants} />
      <motion.path d="M20 182H240" stroke={soft} strokeWidth="1" fill="none" variants={strokeVariants} />
      <motion.path d={rectPath(34, 84, 16, 92)} fill={fill} stroke={ink} strokeWidth="1.6" variants={strokeVariants} />
      <motion.path d="M34 98h16M34 162h16" stroke={soft} strokeWidth="1" fill="none" variants={strokeVariants} />
      <motion.path d={rectPath(52, 60, 20, 116)} fill={fill} stroke={ink} strokeWidth="1.6" variants={strokeVariants} />
      <motion.path d="M52 76h20M52 160h20" stroke={soft} strokeWidth="1" fill="none" variants={strokeVariants} />
      <motion.path d={rectPath(74, 94, 13, 82)} fill={fill} stroke={ink} strokeWidth="1.6" variants={strokeVariants} />
      <motion.path d={rectPath(92, 30, 24, 134)} fill={fill} stroke={accent} strokeWidth="2" variants={strokeVariants} />
      <motion.path d="M92 48h24M92 146h24M98 82h12M98 90h12M98 98h12" stroke={accent} strokeWidth="1.2" fill="none" variants={strokeVariants} />
      <motion.path d="M123 56c8-6 8-18 0-24" stroke={accent} strokeWidth="1.2" strokeDasharray="2 4" fill="none" variants={strokeVariants} />
      <motion.path d={rectPath(124, 74, 17, 102)} fill={fill} stroke={ink} strokeWidth="1.6" variants={strokeVariants} />
      <motion.path d="M124 88h17M124 162h17" stroke={soft} strokeWidth="1" fill="none" variants={strokeVariants} />
      <motion.path d={rectPath(143, 60, 24, 116)} fill={fill} stroke={ink} strokeWidth="1.6" variants={strokeVariants} />
      <motion.path d="M143 78h24M143 160h24" stroke={soft} strokeWidth="1" fill="none" variants={strokeVariants} />
      <motion.path d={rectPath(169, 102, 14, 74)} fill={fill} stroke={ink} strokeWidth="1.6" variants={strokeVariants} />
      <g transform="rotate(14 205 176)">
        <motion.path d={rectPath(192, 70, 18, 106)} fill={fill} stroke={ink} strokeWidth="1.6" variants={strokeVariants} />
        <motion.path d="M192 86h18M192 162h18" stroke={soft} strokeWidth="1" fill="none" variants={strokeVariants} />
      </g>
    </>
  );
}
