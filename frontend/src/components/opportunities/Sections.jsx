/*
  Opportunity.sections: [{kind, title, blocks: [{type: "p" | "li" | "h", text}]}].
  Always plain text from the API, rendered as text (never as HTML).
  Consecutive "li" blocks are grouped into one list.
*/
function groupBlocks(blocks) {
  const groups = [];
  for (const block of blocks || []) {
    const last = groups[groups.length - 1];
    if (block.type === "li") {
      if (last?.type === "ul") last.items.push(block.text);
      else groups.push({ type: "ul", items: [block.text] });
    } else {
      groups.push(block);
    }
  }
  return groups;
}

function Blocks({ blocks }) {
  return groupBlocks(blocks).map((g, i) => {
    if (g.type === "ul") {
      return (
        <ul key={i} className="list-disc space-y-1 pl-5">
          {g.items.map((t, j) => <li key={j}>{t}</li>)}
        </ul>
      );
    }
    if (g.type === "h") return <h4 key={i} className="pt-2 font-semibold text-text">{g.text}</h4>;
    return <p key={i}>{g.text}</p>;
  });
}

export default function Sections({ sections, description }) {
  if (!sections?.length) {
    if (!description) return null;
    return (
      <section>
        <h2 className="mb-3 text-lg font-semibold">About this opportunity</h2>
        <div className="max-w-prose space-y-3 leading-relaxed whitespace-pre-line">{description}</div>
      </section>
    );
  }
  return (
    <div className="space-y-8">
      {sections.map((s, i) => (
        <section key={`${s.kind}-${i}`} id={s.kind}>
          <h2 className="mb-3 text-lg font-semibold">{s.title}</h2>
          <div className="max-w-prose space-y-3 leading-relaxed">
            <Blocks blocks={s.blocks} />
          </div>
        </section>
      ))}
    </div>
  );
}
