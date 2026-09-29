type Message = { id: string; subject: string; unread: boolean; archived: boolean };

export function InboxList({ messages }: { messages: Message[] }) {
  const visible = messages.filter((message) => !message.archived);
  return (
    <ul>
      {visible.map((message) => (
        <li key={message.id}>
          {message.unread && <span data-cy="unread-dot" />}
          {message.subject}
        </li>
      ))}
    </ul>
  );
}
