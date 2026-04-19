export default function BackgroundGlow() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      <div className="absolute inset-0 bg-grain opacity-80" />

      <div className="absolute -left-[30%] -top-[12%] h-[94vh] w-[76vw] animate-floatAura rounded-[48%] border border-[#c7b4ff]/55 bg-transparent shadow-[0_0_150px_rgba(184,160,255,0.38)] blur-[2px]" />
      <div className="absolute -left-[24%] -top-[5%] h-[96vh] w-[72vw] animate-pulseGlow rounded-[46%] border-[20px] border-[#fff7ec]/88 bg-transparent shadow-[0_0_200px_rgba(231,196,120,0.38)] blur-sm" />
      <div className="absolute -left-[7%] top-[9%] h-[72vh] w-[46vw] rounded-[44%] bg-[radial-gradient(circle,rgba(191,168,255,0.26),rgba(255,247,239,0))] blur-3xl" />
      <div className="absolute bottom-[-24%] right-[-10%] h-[54vh] w-[42vw] rounded-full bg-[radial-gradient(circle,rgba(242,218,153,0.24),rgba(255,248,240,0))] blur-3xl" />
    </div>
  );
}
