import { useEffect, useRef, useState } from "react";

export function useCountUp(target, duration = 700) {
  const [value, setValue] = useState(0);
  const frameRef = useRef();

  useEffect(() => {
    const end = Number(target) || 0;
    const start = performance.now();

    function tick(now) {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setValue(Math.round(end * eased));
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick);
      }
    }

    frameRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameRef.current);
  }, [target, duration]);

  return value;
}
