import { motion } from "framer-motion";
import { rectPath, strokeVariants, fillVariants } from "./SceneFrame";

const ink = "rgb(var(--scene-ink))";
const soft = "rgb(var(--scene-ink-soft))";
const fill = "rgb(var(--scene-fill))";
const accent = "rgb(var(--accent))";

export function SceneProblem() {
  return (
    <>
      <g transform="rotate(-12 70 95)">
        <motion.path d={rectPath(40, 55, 62, 84)} fill={fill} stroke={ink} strokeWidth="1.6" strokeLinejoin="round" variants={strokeVariants} />
        <motion.path d="M50 75h42M50 87h36M50 99h40M50 111h28" stroke={soft} strokeWidth="1.2" fill="none" variants={strokeVariants} />
      </g>
      <g transform="rotate(9 150 85)">
        <motion.path d={rectPath(120, 45, 62, 84)} fill={fill} stroke={ink} strokeWidth="1.6" strokeLinejoin="round" variants={strokeVariants} />
        <motion.path d="M130 65h42M130 77h30M130 89h40M130 101h34" stroke={soft} strokeWidth="1.2" fill="none" variants={strokeVariants} />
      </g>
      <g transform="rotate(20 190 135)">
        <motion.path d={rectPath(160, 100, 58, 76)} fill={fill} stroke={ink} strokeWidth="1.6" strokeLinejoin="round" variants={strokeVariants} />
        <motion.path d="M169 118h38M169 130h30M169 142h36" stroke={soft} strokeWidth="1.2" fill="none" variants={strokeVariants} />
      </g>
      <motion.path d="M40 176h40l5-12h30l5 12h34" stroke={soft} strokeWidth="1.2" fill="none" variants={strokeVariants} />
      <motion.path d="M176 30c0-16 24-16 24 0c0 11-13 13-13 26" stroke={accent} strokeWidth="2.2" fill="none" strokeLinecap="round" variants={strokeVariants} />
      <motion.circle cx="187" cy="68" r="1.6" fill={accent} variants={fillVariants} />
    </>
  );
}
