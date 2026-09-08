import { PromptInputBox } from "@/components/ui/ai-prompt-box";

const DemoOne = () => {
  const handleSendMessage = (message: string, files?: File[]) => {
    console.log("Message:", message);
    console.log("Files:", files);
  };

  return (
    <div className="flex w-full min-h-screen justify-center items-center bg-[#080a0a] relative overflow-hidden p-6 font-sans">
      {/* Ambient background glows matching BebshaX research console theme */}
      <div 
        className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[350px] bg-gradient-to-tr from-[#14b8a6]/15 via-[#22d3ee]/10 to-transparent blur-3xl pointer-events-none rounded-full" 
        aria-hidden="true" 
      />
      <div 
        className="absolute bottom-10 right-10 w-[400px] h-[250px] bg-[#10b981]/10 blur-3xl pointer-events-none rounded-full" 
        aria-hidden="true" 
      />

      <div className="relative z-10 p-6 w-full max-w-[640px] flex flex-col items-center gap-6">
        <header className="text-center space-y-2">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[#202727] bg-[#0d1111]/80 text-[#14b8a6] text-xs font-mono tracking-wider uppercase">
            BebshaX · AI Research Prompt Box
          </div>
          <h1 className="text-2xl font-bold text-[#f4f7f7] tracking-tight">
            Synthetic Persona Interview Input
          </h1>
          <p className="text-sm text-[#8d9999] max-w-md">
            Test questions, search research evidence, upload reference imagery, or record audio prompts.
          </p>
        </header>

        {/* AI Prompt Box Component */}
        <div className="w-full">
          <PromptInputBox 
            onSend={handleSendMessage} 
            placeholder="Ask persona about pricing, pain points, or product habits…" 
          />
        </div>

        {/* Demo stock asset recommendations */}
        <footer className="text-xs text-[#5f6b6b] text-center space-y-1">
          <p>Sample reference imagery: Unsplash UX wireframes & persona avatars</p>
          <div className="flex items-center justify-center gap-3 pt-2">
            <a 
              href="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=500&auto=format&fit=crop&q=80" 
              target="_blank" 
              rel="noopener noreferrer" 
              className="text-[#14b8a6] hover:underline"
            >
              Portrait Stock Reference
            </a>
            <span>·</span>
            <a 
              href="https://images.unsplash.com/photo-1581291518857-4e27b48ff24e?w=500&auto=format&fit=crop&q=80" 
              target="_blank" 
              rel="noopener noreferrer" 
              className="text-[#22d3ee] hover:underline"
            >
              Wireframe Stock Reference
            </a>
          </div>
        </footer>
      </div>
    </div>
  );
};

export { DemoOne };
export default DemoOne;
