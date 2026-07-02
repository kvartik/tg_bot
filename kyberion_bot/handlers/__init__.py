from . import people, routine, shifts, start, tasks

routers = [
    start.router,
    shifts.router,
    tasks.router,
    people.router,
    routine.router,
]
