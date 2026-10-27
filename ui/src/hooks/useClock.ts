import { useEffect, useState } from "react";

/** 每秒刷新一次的只读时钟，供状态栏/运行时长使用。 */
export function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);
  return now;
}
