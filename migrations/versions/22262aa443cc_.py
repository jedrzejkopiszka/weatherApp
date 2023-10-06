"""empty message

Revision ID: 22262aa443cc
Revises: 6e2940099b30
Create Date: 2023-10-06 18:12:05.024064

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '22262aa443cc'
down_revision = '6e2940099b30'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('emails',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('city_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['city_id'], ['city.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'city_id')
    )
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('email_notifications')

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_notifications', sa.BOOLEAN(), nullable=True))

    op.drop_table('emails')
    # ### end Alembic commands ###
