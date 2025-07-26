#!/usr/bin/env python3
# -*- coding: UTF-8 -*-


def handle(comment, instruo, komando, ajo):
    print("Translated handler initiated.")

    if ajo.type == 'single':
        ajo.set_status('translated')
    else:  # Defined multiple post.
        pass

    # Update the Ajo and post.
    ajo.update_reddit()

    pass
