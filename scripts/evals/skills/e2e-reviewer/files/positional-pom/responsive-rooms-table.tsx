import { useMediaQuery } from '@rocket.chat/fuselage-hooks';

type RoomCounts = {
	name: string;
	type: string;
	users: number;
	messages: number;
};

export const RoomCountsRow = ({ name, type, users, messages }: RoomCounts) => {
	const showDetails = useMediaQuery('(min-width: 1024px)');

	return (
		<tr aria-label={name}>
			<td>{name}</td>
			<td>{type}</td>
			<td>{users}</td>
			{showDetails && <td>{messages}</td>}
		</tr>
	);
};
