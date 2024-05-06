import csv
import io


def parse_csv_ranking(raw):
    reader = csv.DictReader(io.StringIO(raw))

    show_team = 'Team' in reader.fieldnames
    problems = [reader.fieldnames[i] for i in range(5 if show_team else 4, len(reader.fieldnames), 1)]
    users = []

    for row in reader:
        users.append({
            'username': row['Username'],
            'full_name': row['Full Name'],
            'scores': [float(row[prob]) if row[prob] != '' else 0 for prob in problems],
            'total_score': float(row['Points']),
        })

    users.sort(key=lambda p: p['total_score'], reverse=True)

    return users, problems
