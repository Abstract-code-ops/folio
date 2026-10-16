import { motion } from "framer-motion";
import { rectPath, strokeVariants, fillVariants } from "./SceneFrame";

const ink = "rgb(var(--scene-ink))";
const soft = "rgb(var(--scene-ink-soft))";
const fill = "rgb(var(--scene-fill))";
const accent = "rgb(var(--accent))";

export function SceneHope() {
  return (
    <>
      <motion.path d="M130 168C105 152 73 150 43 158V78C73 70 105 72 130 88Z" fill={fill} stroke={ink} strokeWidth="1.6" strokeLinejoin="round" variants={strokeVariants} />
      <motion.path d="M130 168C155 152 187 150 217 158V78C187 70 155 72 130 88Z" fill={fill} stroke={ink} strokeWidth="1.6" strokeLinejoin="round" variants={strokeVariants} />
      <motion.path d="M130 88V168" stroke={ink} strokeWidth="1.6" fill="none" variants={strokeVariants} />
      <motion.path d="M59 96c20-2 40 0 58 8M59 110c20-2 40 0 58 8M59 124c20-2 40 0 58 8M59 138c16-1 30 0 44 5" stroke={soft} strokeWidth="1.1" fill="none" variants={strokeVariants} />
      <motion.path d="M143 104c18-8 38-10 58-8M143 118c18-8 38-10 58-8M143 132c18-8 38-10 58-8" stroke={soft} strokeWidth="1.1" fill="none" variants={strokeVariants} />
      <motion.path d={rectPath(104, 22, 52, 24)} fill="rgb(var(--bg-surface))" stroke={accent} strokeWidth="1.8" variants={strokeVariants} />
      <motion.text x="130" y="39" textAnchor="middle" fontFamily="Georgia, serif" fontSize="12" fill={accent} variants={fillVariants}>
        p. 12
      </motion.text>
      <motion.path d="M130 46v14" stroke={accent} strokeWidth="1.2" strokeDasharray="2 4" fill="none" variants={strokeVariants} />
    </>
  );
}
