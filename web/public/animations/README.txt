Drop the book loading animation here as: page-flipping.json

Source (free, Lottie Simple License):
  https://lottiefiles.com/free-animation/page-flipping-rbkLoAF6Z1
Download the "Lottie JSON" file and save it as:
  web/public/animations/page-flipping.json

The app fetches /animations/page-flipping.json at runtime and shows a plain
spinner until this file exists, so adding it needs no rebuild — just refresh.

Thinking indicator: uses the useAnimations (MIT) "loading" icon via the
react-useanimations package. No asset needed here.
